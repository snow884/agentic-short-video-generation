import asyncio
import http.cookiejar
import json
import os

import nest_asyncio
from deepagents import create_deep_agent
from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
from langchain_community.tools.playwright.utils import create_async_playwright_browser
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama
from langchain_tavily import TavilySearch

nest_asyncio.apply()

from pathlib import Path
from typing import Optional, Type

from deepagents.backends.filesystem import FilesystemBackend
from langchain.agents.middleware import ToolRetryMiddleware
from langchain.agents.structured_output import ProviderStrategy
from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
from langchain_community.tools.playwright.base import BaseBrowserTool
from langchain_community.tools.playwright.click import ClickTool
from langchain_core.callbacks import CallbackManagerForToolRun
from prefect.logging import get_run_logger
from pydantic import BaseModel, Field


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

    tavity_tools = [
        TavilySearch(
            max_results=5,
            topic="general",
            # include_answer=False,
            # include_raw_content=False,
            # include_images=False,
            # include_image_descriptions=False,
            # search_depth="basic",
            # time_range="day",
            # include_domains=None,
            # exclude_domains=None
        )
    ]

    async_browser = create_async_playwright_browser(
        args=["--disable-gpu", "--no-sandbox"], headless=False
    )

    toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=async_browser)

    # 2. Parse the cookies.txt file
    if extra_cookie_file:
        cookie_jar = http.cookiejar.MozillaCookieJar()
        cookie_jar.load(extra_cookie_file, ignore_discard=True, ignore_expires=True)

        cookie_list = []
        for cookie in cookie_jar:
            cookie_dict = {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": cookie.secure,
                "httpOnly": cookie.has_nonstandard_attr("HttpOnly"),
            }
            if cookie.expires:
                cookie_dict["expires"] = cookie.expires
            cookie_list.append(cookie_dict)

        # 3. Add to the Playwright browser context
        # browser_context = async_browser.contexts[0]  # or a newly created context

        context = await async_browser.new_context()

        await context.add_cookies(cookie_list)

    browser_tools = toolkit.get_tools()

    class ForceClickTool(ClickTool):
        name: str = "force_click_element"
        description: str = (
            "Use this to force-click an element via JavaScript when standard clicks"
            " fail."
        )

        def _run(
            self, selector: str, run_manager: Optional[CallbackManagerForToolRun] = None
        ) -> str:
            # Resolves via the underlying sync/async Playwright page instance

            context = async_browser.new_context()

            page = context.pages[0]

            try:
                # Force click bypasses standard visibility/interactivity checks
                page.click(selector, force=True)
                return f"Successfully force-clicked element: {selector}"
            except Exception:
                # Ultimate fallback: Evaluate direct browser JavaScript execution
                try:
                    page.evaluate(f"document.querySelector('{selector}').click()")
                    return f"Successfully dispatched JS click to element: {selector}"
                except Exception as e:
                    return f"Failed to click element: {str(e)}"

    browser_tools.append(
        ForceClickTool(
            sync_browser=toolkit.sync_browser, async_browser=toolkit.async_browser
        )
    )

    # 1. Define the input validation schema for the LLM
    class UploadFileInput(BaseModel):
        selector: str = Field(
            description=(
                "The CSS selector for the file input element. Usually"
                " 'input[type=file]'."
            )
        )
        file_path: str = Field(
            description="The absolute local system path to the video/file to upload."
        )

    # 2. Build the Custom Playwright upload tool inherited from LangChain's base
    class PlaywrightUploadFileTool(BaseBrowserTool):
        name: str = "upload_file"
        description: str = (
            "Use this tool to upload a video or file directly to an HTML input tag. Do"
            " NOT click the button first; use this tool directly with the target file"
            " path."
        )
        args_schema: Type[BaseModel] = UploadFileInput

        def _run(
            self,
            selector: str,
            file_path: str,
            run_manager: Optional[CallbackManagerForToolRun] = None,
        ) -> str:
            # Access active browser context (supports sync and async modes)
            if self.sync_browser:

                context = async_browser.new_context()

                page = context.pages[0]

                # page = self.sync_browser.pages[0]
                try:
                    page.wait_for_selector(selector, state="attached", timeout=5000)
                    page.set_input_files(selector, file_path)  # Direct injection
                    return (
                        f"Successfully attached file {file_path} to selector"
                        f" '{selector}'"
                    )
                except Exception as e:
                    return f"Sync file upload failed: {str(e)}"
            else:
                return "This tool instance requires a synchronous browser context."

        # If your agent setup is using AsyncPlaywright, use this method instead:
        async def _arun(
            self,
            selector: str,
            file_path: str,
            run_manager: Optional[CallbackManagerForToolRun] = None,
        ) -> str:
            if self.async_browser:
                page = self.async_browser.pages[0]
                try:
                    await page.wait_for_selector(
                        selector, state="attached", timeout=5000
                    )
                    await page.set_input_files(selector, file_path)  # Direct injection
                    return (
                        f"Successfully attached file {file_path} to selector"
                        f" '{selector}'"
                    )
                except Exception as e:
                    return f"Async file upload failed: {str(e)}"
            else:
                return "This tool instance requires an asynchronous browser context."

    browser_tools.append(PlaywrightUploadFileTool(async_browser=toolkit.async_browser))

    model = ChatOllama(
        model=os.environ["RESEARCH_AGENT_MODEL"],
        reasoning=True,
        # temperature=0,
        um_ctx=12288,  # Set context window here
    )
    # model = model.with_structured_output(ReturnClass)

    tavity_tools_str = ", ".join([t.name for t in tavity_tools])
    browser_tools_str = ", ".join([t.name for t in browser_tools])

    system_prompt_params_combined = {
        **system_prompt_params,
        "tavity_tools_str": tavity_tools_str,
        "browser_tools_str": browser_tools_str,
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
        tools=browser_tools + tavity_tools + extra_tools,
        system_prompt=PromptTemplate.from_file(prompt_dir / "sys_prompt.md").format(
            **system_prompt_params_combined
        ),
        response_format=ProviderStrategy(ReturnClass),
        middleware=[
            ToolRetryMiddleware(
                max_retries=3,
                backoff_factor=2.0,
                initial_delay=1.0,
            ),
        ],
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
    json_start = str_message.replace("```json", "").replace("```", "")

    print("Raw response: ", json_start)

    dict_start = json.loads(json_start)

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
