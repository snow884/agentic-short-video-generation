
import requests

requests.post("http://localhost:8000/inference/", json={"image_path": "agentic-tasks/data/video/sad_talker_out/obama.jpg", "audio_path": "data/sample_input/obama.wav", "verbose": True})