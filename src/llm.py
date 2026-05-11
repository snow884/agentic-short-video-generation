    
import os
from typing import Type
from zipfile import Path
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage

from prefect.logging import get_run_logger

def chat_ollama_with_structured_output(user_prompt_params, system_prompt_params, return_class, prompt_dir: Path):

    logger = get_run_logger()

    model = ChatOllama(
        model=os.environ["RESEARCH_AGENT_MODEL"],
        reasoning=True,
        temperature=0,
    )
    model_structured = model.with_structured_output(return_class)
    
    system_prompt = PromptTemplate.from_file(prompt_dir / "sys_prompt.md").format(**system_prompt_params)
    user_prompt = PromptTemplate.from_file(prompt_dir / "user_prompt.md").format(**user_prompt_params)
    
    logger.info("System Prompt: %s", system_prompt)
    logger.info("User Prompt: %s", user_prompt)
    
    messages = [
        SystemMessage(content=system_prompt,),
        HumanMessage(content=user_prompt,)
    ]

    response = model_structured.invoke(messages)
    
    logger.info("Response: %s", response)
    
    logger.info("Raw response from Ollama: %s", response)
    
    return response