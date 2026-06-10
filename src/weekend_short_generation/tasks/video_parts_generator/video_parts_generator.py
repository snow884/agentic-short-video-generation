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


def generate_video(prompt, output_file_path):

    workflow_file = "wan2_2_t2v_lightx2v_lora_distorch.json"

    def positive_prompt_modification(node):
        node["inputs"]["text"] = prompt
        print(f"new prompt: {node['inputs']['text']}")
        return node

    def negative_prompt_modification(node):
        node["inputs"]["text"] = (
            "Static, person walking backwards, person not moving, static scene,"
            " blurred, deformed hands, extra fingers, low quality, CGI look, cartoon,"
            " anime, static background, bad anatomy, slow motion, serious tone, dark"
            " lighting, watermark, text, signature."
        )
        print(f"new prompt: {node['inputs']['text']}")
        return node

    prompt_modifications = {
        "3": positive_prompt_modification,
        "4": negative_prompt_modification,
    }

    run_comfyui_workflow(
        workflow_file, output_file_path, prompt_modifications, output_node_id="61"
    )


def generate_narrator_video(input_audio_file, output_file_path):

    workflow_file = "float_va_dynamic_emo.json"

    def upload_audio_to_comfy(file_path):
        url = f"http://{SERVER_ADDRESS}/upload/image"

        base_filename = os.path.basename(file_path)

        # ComfyUI natively processes audio/video uploads via the image endpoint
        with open(file_path, "rb") as f:
            files = {"image": (base_filename, f, "audio/wav")}
            # Use overwrite=true if you want to replace an existing file with the same name
            data = {"overwrite": "true"}

            response = requests.post(url, files=files, data=data)

        if response.status_code == 200:
            result = response.json()
            print("Upload successful:", result)
            # Returns the filename saved inside ComfyUI's input directory
            return result.get("name")
        else:
            raise Exception(f"Failed to upload media: {response.text}")

    # 2. Upload the file and capture the safe server filename
    server_filename = upload_audio_to_comfy(input_audio_file)

    def input_audio_modification(node):

        # 4. Point your specific audio node to the uploaded file name
        # Note: Locate your exact node ID and target parameter (e.g., 'audio', 'vhs_audio', etc.)

        node["inputs"]["audio"] = server_filename

        return node

    prompt_modifications = {
        "17": input_audio_modification,
    }

    run_comfyui_workflow(
        workflow_file, output_file_path, prompt_modifications, output_node_id="57"
    )


def run_comfyui_workflow(
    workflow_file, output_file_path, prompt_modifications, output_node_id="3"
):

    # 1. Load the exported API JSON
    current_dir = Path(__file__).resolve().parent
    with open(
        current_dir / "workflow_files" / workflow_file, "r", encoding="utf-8"
    ) as f:
        prompt_workflow = json.load(f)

    for node_id, node in prompt_workflow.items():

        if node_id in prompt_modifications.keys():
            print(f"Node ID {node_id} has a prompt modification. Applying it.")
            prompt_workflow[node_id] = prompt_modifications[node_id](
                node
            )  # Apply the modification function to the node
        else:
            print(
                f"Node ID {node_id} has no prompt modification. Keeping original"
                " prompt."
            )

    def queue_prompt(prompt, client_id):
        """Sends the workflow JSON payload to the ComfyUI queue."""
        p = {"prompt": prompt, "client_id": client_id}
        data = json.dumps(p).encode("utf-8")
        req = requests.post(f"http://{SERVER_ADDRESS}/prompt", data=data)
        print(f"Prompt queued with status code: {req.status_code}")
        print(f"Response: {req.text}")
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
            print(node_output)
            if (
                node_id == output_node_id
            ):  # Check the specific node ID that generates the video

                if "gifs" in node_output:
                    file_info = node_output["gifs"][0]
                    break
                elif "videos" in node_output:
                    file_info = node_output["videos"][0]
                    break
                elif "images" in node_output:
                    file_info = node_output["images"][0]
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

        generate_video(
            segment.scene_description,
            os.path.join(
                parent_dir, f"data/video/t2v_{video.id}_output_{segment.id}.mp4"
            ),
        )

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

    video_path = os.path.join(parent_dir, f"data/video/narrator_video_{video.id}.mp4")
    generate_narrator_video(
        os.path.join(parent_dir, combined_audio_path),
        video_path,
    )

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
