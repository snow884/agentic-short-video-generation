import os

import requests

from weekend_short_generation.tasks.video_parts_generator.video_parts_generator import (
    run_comfyui_workflow,
)

COMFYUI_SERVER = "http://localhost:8080"


def generate_video(prompt, output_file_path):

    workflow_file = "wan2_2_t2v_lightx2v_lora_distorch.json"

    def positive_prompt_modification(node):
        node["inputs"]["text"] = prompt
        print(f"new prompt: {node['inputs']['text']}")
        return node

    def negative_prompt_modification(node):
        node["inputs"]["text"] = (
            "Static, person not moving, static scene, blurred, deformed hands, extra"
            " fingers, low quality, CGI look, cartoon, anime, static background, bad"
            " anatomy, slow motion, serious tone, dark lighting, watermark, text,"
            " signature."
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
        url = f"{COMFYUI_SERVER}/upload/image"

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


if __name__ == "__main__":
    generate_narrator_video(
        "/home/adaivasnky/Documents/src/agentic_tasks/agentic-tasks/data/audio/event_5_segment_7d4a6ea913f6098f650f3464be0ce86a9c3260f6bd7cc3f98b25dd75fe6513da.wav",
        "/home/adaivasnky/Documents/src/agentic_tasks/agentic-tasks/data/video/test.mp4",
    )
