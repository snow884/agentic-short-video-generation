import asyncio
import json
import logging
import os
import re

import nest_asyncio
from deepagents import create_deep_agent
from langchain_core.prompts import PromptTemplate

nest_asyncio.apply()

from pathlib import Path

from deepagents.backends.filesystem import FilesystemBackend
from langchain.agents.structured_output import ToolStrategy
from langchain_ollama import ChatOllama
from prefect.logging import get_run_logger

# Default runtime settings tuned for 2x RTX 5070 (12GB each).
DEFAULT_OLLAMA_CONTEXT_TOKENS = 16 * 1024
DEFAULT_OLLAMA_KEEP_ALIVE = "20m"
DEFAULT_OLLAMA_NUM_PREDICT = 4096
DEFAULT_RESEARCH_AGENT_MODEL = "qwen3.6:27b"


def _dual_gpu_ollama_runtime_defaults() -> dict:
    """Builds Ollama runtime options optimized for dual 12GB GPUs.

    All values can be overridden via environment variables.
    """

    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0,1")
    os.environ.setdefault("OLLAMA_SCHED_SPREAD", "1")

    num_ctx = int(
        os.getenv("RESEARCH_AGENT_NUM_CTX", str(DEFAULT_OLLAMA_CONTEXT_TOKENS))
    )
    num_predict = int(
        os.getenv("RESEARCH_AGENT_NUM_PREDICT", str(DEFAULT_OLLAMA_NUM_PREDICT))
    )
    keep_alive = os.getenv("RESEARCH_AGENT_KEEP_ALIVE", DEFAULT_OLLAMA_KEEP_ALIVE)
    reasoning = os.getenv("RESEARCH_AGENT_REASONING", "0") == "1"

    return {
        "num_ctx": num_ctx,
        "num_predict": num_predict,
        "keep_alive": keep_alive,
        "reasoning": reasoning,
    }


def _extract_json_payload(message: str) -> str:
    """Extract the first valid JSON payload from an LLM response string."""

    message = message.strip()

    # Prefer fenced JSON blocks if present.
    fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", message, flags=re.DOTALL)
    for block in fenced_blocks:
        block = block.strip()
        if not block:
            continue
        try:
            json.loads(block)
            return block
        except json.JSONDecodeError:
            continue

    # Fast path for pure JSON output.
    try:
        json.loads(message)
        return message
    except json.JSONDecodeError:
        pass

    # Fallback: find the first decodable object/array within mixed text.
    decoder = json.JSONDecoder()
    for idx, char in enumerate(message):
        if char not in "[{":
            continue
        try:
            _, end = decoder.raw_decode(message[idx:])
            return message[idx : idx + end]
        except json.JSONDecodeError:
            continue

    raise json.JSONDecodeError("No JSON payload found in model response", message, 0)


def _coerce_message_to_text(message_content) -> str:
    """Normalizes message content into text for JSON extraction."""
    if isinstance(message_content, list):
        return "\n".join(
            chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
            for chunk in message_content
        )
    return str(message_content)


def _extract_typed_response_from_result(result, ReturnClass):
    """Extracts and validates JSON from any message in the agent result."""
    messages = result.get("messages") or []

    # 1) Best-effort recovery from tool-call payloads (common when final
    # assistant content is empty but structured args were produced).
    check_script_candidates_by_call_id = {}
    check_script_candidates_in_order = []

    for message in messages:
        tool_calls = getattr(message, "tool_calls", None) or []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            if tool_call.get("name") != "check_script":
                continue
            args = tool_call.get("args") or {}
            if not isinstance(args, dict):
                continue
            candidate = args.get("video_script")
            if not isinstance(candidate, dict):
                continue

            call_id = tool_call.get("id")
            if isinstance(call_id, str) and call_id:
                check_script_candidates_by_call_id[call_id] = candidate
            check_script_candidates_in_order.append(candidate)

    # Prefer scripts explicitly acknowledged by the check_script tool as success.
    for message in messages:
        tool_call_id = getattr(message, "tool_call_id", None)
        content = _coerce_message_to_text(getattr(message, "content", "")).strip()
        if content.lower() != "success":
            continue
        if (
            isinstance(tool_call_id, str)
            and tool_call_id in check_script_candidates_by_call_id
        ):
            return ReturnClass(**check_script_candidates_by_call_id[tool_call_id])

    # Otherwise, use the newest script candidate from check_script args.
    for candidate in reversed(check_script_candidates_in_order):
        try:
            return ReturnClass(**candidate)
        except (TypeError, ValueError):
            continue

    # Prefer newest messages first.
    for message in reversed(messages):
        content = getattr(message, "content", message)
        content_text = _coerce_message_to_text(content).strip()
        if not content_text:
            continue

        try:
            json_payload = _extract_json_payload(content_text)
            payload_dict = json.loads(json_payload)
            return ReturnClass(**payload_dict)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    raise json.JSONDecodeError(
        "No JSON payload found in model response",
        _coerce_message_to_text(getattr(messages[-1], "content", ""))
        if messages
        else "",
        0,
    )


def _response_truncated(result) -> bool:
    """Checks whether the model likely stopped due to output token limit."""
    messages = result.get("messages") or []
    if not messages:
        return False

    last_message = messages[-1]
    metadata = getattr(last_message, "response_metadata", {}) or {}
    return metadata.get("done_reason") == "length"


def _is_transient_transport_error(exc: Exception) -> bool:
    """Return True for network/protocol errors that are safe to retry."""
    error_name = exc.__class__.__name__.lower()
    error_text = str(exc).lower()

    retry_markers = (
        "connecterror",
        "remoteprotocolerror",
        "server disconnected",
        "all connection attempts failed",
        "connection refused",
        "connection reset",
        "connection aborted",
        "read timeout",
        "connect timeout",
        "temporarily unavailable",
        "broken pipe",
    )

    return any(marker in error_name or marker in error_text for marker in retry_markers)


def _create_chat_ollama(model_name: str, ollama_runtime: dict) -> ChatOllama:
    """Creates a ChatOllama model with shared runtime settings."""
    return ChatOllama(
        model=model_name,
        reasoning=ollama_runtime["reasoning"],
        temperature=0,
        num_predict=ollama_runtime["num_predict"],
        num_ctx=ollama_runtime["num_ctx"],
        keep_alive=ollama_runtime["keep_alive"],
    )


async def run_agent(
    user_prompt_params: dict = {
        "town_name": "Batavia",
        "town_state": "NY",
        "weekend_date": "2026-05-16",
    },
    system_prompt_params: dict = {},
    ReturnClass=None,
    prompt_dir=None,
    extra_tools=[],
    extra_cookie_file=None,
):

    try:
        logger = get_run_logger()
    except Exception as exc:
        if "no active flow or task run context" in str(exc).lower():
            logger = logging.getLogger(__name__)
        else:
            raise

    # tavity_tools = [
    #     TavilySearch(
    #         max_results=5,
    #         topic="general",
    #         # include_answer=False,
    #         # include_raw_content=False,
    #         # include_images=False,
    #         # include_image_descriptions=False,
    #         # search_depth="basic",
    #         # time_range="day",
    #         # include_domains=None,
    #         # exclude_domains=None
    #     )
    # ]

    # custom_ua = (
    #     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like"
    #     " Gecko) Chrome/131.0.0.0 Safari/537.36"
    # )
    # width, height = 1920, 1080

    # async_browser = create_async_playwright_browser(
    #     headless=False,
    #     args=[
    #         "--disable-gpu",
    #         "--no-sandbox",
    #         f"--user-agent={custom_ua}",
    #         f"--window-size={width},{height}",
    #         "--start-maximized",
    #         "--disable-web-security",  # Bypasses CSP/Same-Origin Policy
    #         "--disable-javascript",
    #     ],
    # )

    # toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=async_browser)

    # context = None

    # # 2. Parse the cookies.txt file
    # if extra_cookie_file:
    #     cookie_jar = http.cookiejar.MozillaCookieJar()
    #     cookie_jar.load(extra_cookie_file, ignore_discard=True, ignore_expires=True)

    #     cookie_list = []
    #     for cookie in cookie_jar:
    #         cookie_dict = {
    #             "name": cookie.name,
    #             "value": cookie.value,
    #             "domain": cookie.domain,
    #             "path": cookie.path,
    #             "secure": cookie.secure,
    #             "httpOnly": cookie.has_nonstandard_attr("HttpOnly"),
    #         }
    #         if cookie.expires:
    #             cookie_dict["expires"] = cookie.expires
    #         cookie_list.append(cookie_dict)

    #     # 3. Add to the Playwright browser context
    #     # browser_context = async_browser.contexts[0]  # or a newly created context

    #     context = await async_browser.new_context()

    #     await context.add_cookies(cookie_list)

    # if not context:
    #     context = await async_browser.new_context()

    # await context.add_init_script(
    #     "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    # )

    # browser_tools = toolkit.get_tools()

    # class ForceClickTool(ClickTool):
    #     name: str = "force_click_element"
    #     description: str = (
    #         "Use this to force-click an element via JavaScript when standard clicks"
    #         " fail."
    #     )

    #     def _run(
    #         self, selector: str, run_manager: Optional[CallbackManagerForToolRun] = None
    #     ) -> str:
    #         # Resolves via the underlying sync/async Playwright page instance

    #         context = async_browser.new_context()

    #         page = context.pages[0]

    #         try:
    #             # Force click bypasses standard visibility/interactivity checks
    #             page.click(selector, force=True)
    #             return f"Successfully force-clicked element: {selector}"
    #         except Exception:
    #             # Ultimate fallback: Evaluate direct browser JavaScript execution
    #             try:
    #                 page.evaluate(f"document.querySelector('{selector}').click()")
    #                 return f"Successfully dispatched JS click to element: {selector}"
    #             except Exception as e:
    #                 return f"Failed to click element: {str(e)}"

    # browser_tools.append(
    #     ForceClickTool(
    #         sync_browser=toolkit.sync_browser, async_browser=toolkit.async_browser
    #     )
    # )

    # # 1. Define the input validation schema for the LLM
    # class UploadFileInput(BaseModel):
    #     selector: str = Field(
    #         description=(
    #             "The CSS selector for the file input element. Usually"
    #             " 'input[type=file]'."
    #         )
    #     )
    #     file_path: str = Field(
    #         description="The absolute local system path to the video/file to upload."
    #     )

    # # 2. Build the Custom Playwright upload tool inherited from LangChain's base
    # class PlaywrightUploadFileTool(BaseBrowserTool):
    #     name: str = "upload_file"
    #     description: str = (
    #         "Use this tool to upload a video or file directly to an HTML input tag. Do"
    #         " NOT click the button first; use this tool directly with the target file"
    #         " path."
    #     )
    #     args_schema: Type[BaseModel] = UploadFileInput

    #     def _run(
    #         self,
    #         selector: str,
    #         file_path: str,
    #         run_manager: Optional[CallbackManagerForToolRun] = None,
    #     ) -> str:
    #         # Access active browser context (supports sync and async modes)
    #         if self.sync_browser:

    #             context = async_browser.new_context()

    #             page = context.pages[0]

    #             # page = self.sync_browser.pages[0]
    #             try:
    #                 page.wait_for_selector(selector, state="attached", timeout=5000)
    #                 page.set_input_files(selector, file_path)  # Direct injection
    #                 return (
    #                     f"Successfully attached file {file_path} to selector"
    #                     f" '{selector}'"
    #                 )
    #             except Exception as e:
    #                 return f"Sync file upload failed: {str(e)}"
    #         else:
    #             return "This tool instance requires a synchronous browser context."

    #     # If your agent setup is using AsyncPlaywright, use this method instead:
    #     async def _arun(
    #         self,
    #         selector: str,
    #         file_path: str,
    #         run_manager: Optional[CallbackManagerForToolRun] = None,
    #     ) -> str:
    #         if self.async_browser:
    #             # page = self.async_browser.pages[0]
    #             context = await async_browser.new_context()

    #             page = await context.pages[0]

    #             try:
    #                 await page.wait_for_selector(
    #                     selector, state="attached", timeout=5000
    #                 )
    #                 await page.set_input_files(selector, file_path)  # Direct injection
    #                 return (
    #                     f"Successfully attached file {file_path} to selector"
    #                     f" '{selector}'"
    #                 )
    #             except Exception as e:
    #                 return f"Async file upload failed: {str(e)}"
    #         else:
    #             return "This tool instance requires an asynchronous browser context."

    # browser_tools.append(PlaywrightUploadFileTool(async_browser=toolkit.async_browser))

    ollama_runtime = _dual_gpu_ollama_runtime_defaults()

    configured_model = os.getenv("RESEARCH_AGENT_MODEL", DEFAULT_RESEARCH_AGENT_MODEL)
    fallback_model = os.getenv(
        "RESEARCH_AGENT_FALLBACK_MODEL", DEFAULT_RESEARCH_AGENT_MODEL
    )

    model = _create_chat_ollama(configured_model, ollama_runtime)
    # model = model.with_structured_output(ReturnClass)

    # model = ChatGoogleGenerativeAI(
    #     model="gemini-3.1-pro-preview",
    #     thinking_level=(  # Enables structured thinking capabilities if supported
    #         "high"  # Options: "none", "low", "medium", "high"
    #     ),
    #     temperature=1.2,
    # )

    # tavity_tools_str = ", ".join([t.name for t in tavity_tools])
    # browser_tools_str = ", ".join([t.name for t in browser_tools])

    system_prompt_params_combined = {
        **system_prompt_params,
        # "tavity_tools_str": tavity_tools_str,
        # "browser_tools_str": browser_tools_str,
    }

    logger.info("system prompt: ")
    logger.info(
        PromptTemplate.from_file(prompt_dir / "sys_prompt.md").format(
            **system_prompt_params_combined
        )
    )

    logger.info("user prompt: ")
    logger.info(
        PromptTemplate.from_file(prompt_dir / "user_prompt.md").format(
            **user_prompt_params
        )
    )

    parent_dir = Path(__file__).parent.parent.resolve()

    def _build_agent_chain(chat_model):
        return create_deep_agent(
            model=chat_model,
            # tools=browser_tools + tavity_tools + extra_tools,
            tools=extra_tools,
            system_prompt=PromptTemplate.from_file(prompt_dir / "sys_prompt.md").format(
                **system_prompt_params_combined
            ),
            response_format=ToolStrategy(ReturnClass),
            # response_format=ReturnClass,
            # middleware=[
            #     ToolRetryMiddleware(
            #         max_retries=3,
            #         backoff_factor=2.0,
            # ctx        initial_delay=1.0,
            #     ),
            # ],
            debug=True,
            cache=None,
            backend=FilesystemBackend(root_dir=parent_dir),
        )

    agent_chain = _build_agent_chain(model)
    base_user_prompt = PromptTemplate.from_file(prompt_dir / "user_prompt.md").format(
        **user_prompt_params
    )
    max_attempts = int(os.getenv("RESEARCH_AGENT_JSON_RETRIES", "3"))
    last_error = None
    previous_attempt_was_truncated = False

    for attempt in range(1, max_attempts + 1):
        messages = [("user", base_user_prompt)]
        if attempt > 1:
            retry_instruction = (
                "Return only one compact valid JSON object that matches the requested"
                " schema. Do not include markdown, prose, or reasoning. Keep values"
                " concise to fit within output limits."
            )
            if previous_attempt_was_truncated:
                retry_instruction += (
                    " Your previous output was truncated; prioritize completing the"
                    " JSON object."
                )
            messages.append(
                (
                    "user",
                    retry_instruction,
                )
            )

        try:
            result = await agent_chain.ainvoke({"messages": messages})
        except Exception as exc:
            error_text = str(exc).lower()
            model_missing = "model" in error_text and "not found" in error_text
            can_fallback = configured_model != fallback_model
            transient_transport = _is_transient_transport_error(exc)

            if model_missing and can_fallback:
                logger.warning(
                    "Configured model '%s' is unavailable. Falling back to '%s'.",
                    configured_model,
                    fallback_model,
                )
                configured_model = fallback_model
                model = _create_chat_ollama(configured_model, ollama_runtime)
                agent_chain = _build_agent_chain(model)
                continue

            if transient_transport and attempt < max_attempts:
                backoff_seconds = min(2 ** (attempt - 1), 8)
                logger.warning(
                    "Attempt %s/%s: transient model transport error (%s). "
                    "Retrying in %ss...",
                    attempt,
                    max_attempts,
                    exc,
                    backoff_seconds,
                )
                await asyncio.sleep(backoff_seconds)
                agent_chain = _build_agent_chain(model)
                continue

            if transient_transport:
                raise RuntimeError(
                    "Model transport failed repeatedly while calling Ollama. "
                    "Check Ollama server stability and model memory pressure."
                ) from exc

            raise

        if "structured_response" in result:
            return result["structured_response"]

        try:
            return _extract_typed_response_from_result(result, ReturnClass)
        except json.JSONDecodeError as exc:
            last_error = exc
            previous_attempt_was_truncated = _response_truncated(result)
            logger.warning(
                "Attempt %s/%s: failed to extract JSON response (%s)",
                attempt,
                max_attempts,
                exc,
            )

    if last_error:
        raise last_error

    raise RuntimeError(
        "Failed to parse model response and no structured output returned."
    )


def run_agent_sync(
    user_prompt_params: dict = {
        "town_name": "Batavia",
        "town_state": "NY",
        "weekend_date": "2026-05-16",
    },
    system_prompt_params: dict = {},
    ReturnClass=None,
    prompt_dir=None,
    extra_tools=[],
    extra_cookie_file=None,
):

    return asyncio.run(
        run_agent(
            user_prompt_params=user_prompt_params,
            system_prompt_params=system_prompt_params,
            ReturnClass=ReturnClass,
            prompt_dir=prompt_dir,
            extra_tools=extra_tools,
            extra_cookie_file=extra_cookie_file,
        )
    )


if __name__ == "__main__":
    run_agent_sync()
