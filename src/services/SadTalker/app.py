
from typing import Any, Dict

from inference import main 

from fastapi import FastAPI, Body

app = FastAPI()

@app.post("/inference/")
def inference(args: Dict[str, Any] = Body(...)):
    try:
        save_dir = main(**args) 
    except Exception as e:
        return {"error": str(e)}
    return {"save_dir": save_dir}