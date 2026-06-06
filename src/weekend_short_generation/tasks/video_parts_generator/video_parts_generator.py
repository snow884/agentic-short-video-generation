import json
import os

from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

import requests
from prefect import task
from pydub import AudioSegment

from sql_utils import get_db
from tables import Events, Video, VideoSegments

VID_HEIGHT = int(1920 / 2)
VID_WIDTH = int(1080 / 2)

import json
import uuid

import requests
import websocket  # pip install websocket-client

# Configuration
SERVER_ADDRESS = (  # Update if your ComfyUI server is running on a different address or port
    "localhost:8080"
)
CLIENT_ID = str(uuid.uuid4())
OUTPUT_VIDEO_PATH = "generated_video.mp4"


def run_comfyui_workflow(workflow_file, output_file_path, prompt_modifications):

    # 1. Load the exported API JSON
    current_dir = Path(__file__).resolve().parent
    with open(
        current_dir / "workflow_files" / workflow_file, "r", encoding="utf-8"
    ) as f:
        prompt_workflow = json.load(f)

    for node in prompt_workflow.get("nodes", []):

        if node.get("title") == "Positive Prompt":
            # Assuming the prompt is in the "inputs" under "text"
            if "inputs" in node and "text" in node["inputs"]:
                original_prompt = node["inputs"]["text"]
                modified_prompt = prompt_modifications.get(node["id"], original_prompt)
                node["inputs"]["text"] = modified_prompt
                print(
                    f"Modified Node ID {node['id']} prompt from: '{original_prompt}'"
                    f" to: '{modified_prompt}'"
                )

    def queue_prompt(prompt, client_id):
        """Sends the workflow JSON payload to the ComfyUI queue."""
        p = {"prompt": prompt, "client_id": client_id}
        data = json.dumps(p).encode("utf-8")
        req = requests.post(f"http://{SERVER_ADDRESS}/prompt", data=data)
        return req.json()

    def download_file(filename, subfolder, folder_type):
        """Downloads the file from the ComfyUI output directory."""
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        response = requests.get(f"http://{SERVER_ADDRESS}/view", params=params)
        if response.status_code == 200:
            with open(output_file_path, "wb") as f:
                f.write(response.content)
            print(f"✅ Video successfully saved to: {output_file_path}")
        else:
            print(f"❌ Failed to download file. Status: {response.status_code}")

    def track_and_download():
        """Connects via WebSockets, tracks execution, and triggers the download."""
        # Establish WebSocket connection
        ws = websocket.WebSocket()
        ws.connect(f"ws://{SERVER_ADDRESS}/ws?clientId={CLIENT_ID}")

        # Queue the workflow execution
        print("🚀 Submitting workflow to ComfyUI...")
        prompt_response = queue_prompt(prompt_workflow, CLIENT_ID)
        prompt_id = prompt_response.get("prompt_id")
        print(f"🎫 Prompt ID Queued: {prompt_id}")

        # Listen to server events
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)

                # Track execution progress
                if message["type"] == "executing":
                    data = message["data"]
                    if data["node"] is None and data["prompt_id"] == prompt_id:
                        print("🏁 Execution complete! Fetching metadata...")
                        break  # Total execution finished
                    elif data["prompt_id"] == prompt_id:
                        print(f"⏳ Currently processing Node ID: {data['node']}")

        # Request historical outputs for this prompt to get the exact filename
        history_req = requests.get(f"http://{SERVER_ADDRESS}/history/{prompt_id}")
        history = history_req.json().get(prompt_id, {})
        outputs = history.get("outputs", {})

        # Extract file details from the node output metadata
        file_info = None
        for node_id, node_output in outputs.items():
            # Adjust 'gifs' or 'videos' depending on the specific custom node used
            if "gifs" in node_output:
                file_info = node_output["gifs"][0]
                break
            elif "videos" in node_output:
                file_info = node_output["videos"][0]
                break

        if file_info:
            filename = file_info.get("filename")
            subfolder = file_info.get("subfolder", "")
            folder_type = file_info.get("type", "output")
            print(f"📦 Found video file: {filename}. Starting download...")
            download_file(filename, subfolder, folder_type)
        else:
            print("❌ Video file info could not be found in execution history.")

        ws.close()

    track_and_download()


@task(task_run_name="video_parts_generator-{video_id}")
def main(video_id):
    session = next(get_db())

    video = session.query(Video).filter(Video.id == video_id).first()

    video_segments = (
        session.query(VideoSegments)
        .filter(VideoSegments.video_id == video.id)
        .order_by(VideoSegments.timestamp)
        .all()
    )

    combined_video = None
    combined_audio = None

    previous_event_id = None

    parent_dir = Path(__file__).parent.parent.parent.parent.parent.resolve()

    for segment in video_segments:

        print(
            f"Segment ID: {segment.id}, Event ID: {segment.event_id}, Timestamp:"
            f" {segment.timestamp}, Script Text: {segment.script_text}, Sound File"
            f" Path: {segment.sound_file_path}, Scene Description:"
            f" {segment.scene_description}, Caption: {segment.caption}"
        )

        sound = AudioSegment.from_file(segment.sound_file_path)

        duration = sound.duration_seconds

        combined_audio = sound if combined_audio is None else combined_audio + sound

        res = requests.post(
            "http://localhost:8001/inference/",
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {
                    "task": "t2v-1.3B",
                    "size": "480*832",
                    "ckpt_dir": "./Wan2.1-T2V-1.3B",
                    "offload_model": True,
                    "t5_cpu": True,
                    "sample_shift": 8,
                    "sample_guide_scale": 6,
                    "prompt": segment.scene_description,
                    "save_file": os.path.join(
                        parent_dir, f"data/video/t2v_{video.id}_output_{segment.id}.mp4"
                    ),
                }
            ),
        )
        if res.status_code != 200:
            raise Exception(f"Error: {res.status_code}, {res.text}")
            return

        segment.video_file_path = os.path.join(
            parent_dir, f"data/video/t2v_{video.id}_output_{segment.id}.mp4"
        )
        session.commit()

    combined_audio_path = os.path.join(
        parent_dir, f"data/video/sad_talker_input/combined_audio{video.id}.wav"
    )

    combined_audio.export(combined_audio_path, format="wav")
    video.audio_file_path = combined_audio_path
    session.commit()

    print(f"Parent directory: {parent_dir}")

    res = requests.post(
        "http://localhost:8000/inference/",
        headers={"Content-Type": "application/json"},
        data=json.dumps(
            {
                "source_image": os.path.join(parent_dir, "data/portraits/anchor2.png"),
                "driven_audio": os.path.join(parent_dir, combined_audio_path),
                "result_dir": os.path.join(parent_dir, "data/video/sad_talker_out"),
                "checkpoint_dir": os.path.join(
                    parent_dir, "src/services/SadTalker/checkpoints"
                ),
                "enhancer": "gfpgan",
            }
        ),
    )

    if res.status_code != 200:
        raise Exception(f"Error: {res.status_code}, {res.text}")
        return

    video_path = res.json()["save_dir"]

    video.audio_file_path = combined_audio_path
    video.sad_talker_video_path = video_path
    session.commit()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    session = next(get_db())
    for e in session.query(Events).all():
        print(e.id, e.event_name)

        main(weekend_id=e.weekend_id, town_id=e.town_id)
