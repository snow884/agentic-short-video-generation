import asyncio
import json
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

    logger = get_run_logger()

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

    model = ChatOllama(
        model="qwen3.6:27b",  # os.environ["RESEARCH_AGENT_MODEL"],
        reasoning=True,
        temperature=0,  # Balanced for creativity and accuracy
        # num_predict=2048,  # Limit max tokens to prevent runaway generation
        # Context Management
        num_ctx=64
        * 1024,  # Adjust based on your memory needs (Default 262k is VRAM heavy)
        # Advanced Settings
        # top_p=0.95,
        # repeat_penalty=1.1,
    )
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

    agent_chain = create_deep_agent(
        model=model,
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
    result = await agent_chain.ainvoke(
        {
            "messages": [
                (
                    "user",
                    PromptTemplate.from_file(prompt_dir / "user_prompt.md").format(
                        **user_prompt_params
                    ),
                )
            ]
        }
    )

    if "structured_response" in result:
        return result["structured_response"]

    str_message = result["messages"][-1].content
    if isinstance(str_message, list):
        str_message = "\n".join(
            chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
            for chunk in str_message
        )
    else:
        str_message = str(str_message)

    json_payload = _extract_json_payload(str_message)
    dict_start = json.loads(json_payload)

    typed_response = ReturnClass(**dict_start)

    return typed_response


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
