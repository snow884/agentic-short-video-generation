

from langchain_ollama import ChatOllama
from langchain_tavily import TavilySearch

from deepagents import create_deep_agent

from langchain_core.prompts import PromptTemplate
    
    
from langchain_community.agent_toolkits import PlayWrightBrowserToolkit

from langchain_community.tools.playwright.utils import (
    create_async_playwright_browser,  
)
from deepagents.backends.filesystem import FilesystemBackend
import os

import asyncio
import nest_asyncio
from pydantic import TypeAdapter
nest_asyncio.apply()

from langchain.agents.middleware import ToolRetryMiddleware
from deepagents.backends.filesystem import FilesystemBackend
from langchain.agents.structured_output import ToolStrategy

async def run_agent(user_prompt_params: dict = {"town_name": "Batavia", "town_state": "NY", "weekend_date": "2026-05-16"}, system_prompt_params: dict = {}, ReturnClass=None, prompt_dir=None, extra_tools=[]):
    
    tavity_tools = [TavilySearch(
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
    )]
    
    async_browser = create_async_playwright_browser(headless=True, args=[])
    
    toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=async_browser)
    browser_tools = toolkit.get_tools()
    

    model = ChatOllama(
        model=os.environ["RESEARCH_AGENT_MODEL"],
        reasoning=True,
        temperature=0,
    )
    #model = model.with_structured_output(ReturnClass)
    
    tavity_tools_str = ', '.join([t.name for t in tavity_tools])
    browser_tools_str =', '.join([t.name for t in browser_tools])
    
    print(PromptTemplate.from_file(prompt_dir / "sys_prompt.md").format(tavity_tools_str=tavity_tools_str, browser_tools_str=browser_tools_str))
    
    agent_chain = create_deep_agent(
        model=model,
        tools=browser_tools+tavity_tools+extra_tools,
        system_prompt=PromptTemplate.from_file(prompt_dir / "sys_prompt.md").format(tavity_tools_str=tavity_tools_str, browser_tools_str=browser_tools_str),
        response_format=ToolStrategy(ReturnClass),
        middleware=[
        ToolRetryMiddleware(
            max_retries=3,
            backoff_factor=2.0,
            initial_delay=1.0,
        ),
    ],
        debug = True
    )
    result = await agent_chain.ainvoke(
        {"messages": [("user", PromptTemplate.from_file(prompt_dir / "user_prompt.md").format(**user_prompt_params))]}
    )
    
    if "structured_response" in result:
        return result["structured_response"]
    
    str = result["messages"][-1].content
    json_start = str.replace("```json", "").replace("```", "")
    
    print("Raw response: ", json_start)
    
    typed_response = ReturnClass.from_json(json_start)

    return typed_response



def run_agent_sync(user_prompt_params: dict = {"town_name": "Batavia", "town_state": "NY", "weekend_date": "2026-05-16"}, system_prompt_params: dict = {}, ReturnClass=None, prompt_dir=None):
    
    return asyncio.run(run_agent(user_prompt_params=user_prompt_params, system_prompt_params=system_prompt_params, ReturnClass=ReturnClass, prompt_dir=prompt_dir))

if __name__ == "__main__":
    run_agent_sync()