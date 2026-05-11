
from typing import Any, Dict

from inference import main 

from fastapi import FastAPI, Body, HTTPException
import argparse

app = FastAPI()

@app.post("/inference/")
def inference(args: Dict[str, Any] = Body(...)):
    args_parsed = argparse.Namespace(**args)
    try:
        save_dir = main(args_parsed) 
    except Exception as e:
        raise HTTPException(status_code=400, detail="Sadtaalker inference failed: " + str(e))
    
    return {"save_dir": save_dir}