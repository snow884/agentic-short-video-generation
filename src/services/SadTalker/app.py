
from typing import Any, Dict

from inference import main 

from fastapi import FastAPI, Body

app = FastAPI()

@app.post("/inference/")
def inference(args: Dict[str, Any] = Body(...)):
    save_dir = main(**args) 
    return {"save_dir": save_dir}