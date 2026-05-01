    
import os
from typing import Type
from zipfile import Path
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage

def chat_ollama_with_structured_output(user_prompt_params, system_prompt_params, return_class, prompt_dir: Path):

    model = ChatOllama(
        model=os.environ["RESEARCH_AGENT_MODEL"],
        reasoning=True,
        temperature=0,
    )
    model_structured = model.with_structured_output(return_class)
    
    system_prompt = PromptTemplate.from_file(prompt_dir / "sys_prompt.md").format(**system_prompt_params)
    user_prompt = PromptTemplate.from_file(prompt_dir / "user_prompt.md").format(**user_prompt_params)
    
    print("System Prompt:", system_prompt)
    print("User Prompt:", user_prompt)
    
    messages = [
        SystemMessage(content=system_prompt,),
        HumanMessage(content=user_prompt,)
    ]

    response = model_structured.invoke(messages)
    
    print(response)
    
    print("Raw response from Ollama:", response)
    
    return response