from ast import Dict
from typing import Any

from inference import main 

from fastapi import FastAPI, Body

app = FastAPI()

@app.post("/inference/")
def read_item(args: Dict[str, Any] = Body(...)):
    save_dir = main(**args) 
    return {"save_dir": save_dir}