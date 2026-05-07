from inference import main 

from fastapi import FastAPI

app = FastAPI()

@app.post("/inference/")
def read_item(args: dict):
    save_dir = main(**args) 
    return {"save_dir": save_dir}