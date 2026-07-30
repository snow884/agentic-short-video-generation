import argparse
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import requests
import websocket  # pip install websocket-client

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

# Configuration
SERVER_ADDRESS = (  # Update if your ComfyUI server is running on a different address or port
    "localhost:8080"
)
CLIENT_ID = str(uuid.uuid4())
OUTPUT_VIDEO_PATH = "generated_video.mp4"


def _format_comfy_execution_error(error_data):
    """Formats an execution_error payload into a readable multiline string."""
    if not error_data:
        return "No execution error details available."

    lines = [
        f"prompt_id: {error_data.get('prompt_id')}",
        f"node_id: {error_data.get('node_id')}",
        f"node_type: {error_data.get('node_type')}",
        f"exception_type: {error_data.get('exception_type')}",
        f"exception_message: {error_data.get('exception_message')}",
    ]

    traceback_lines = error_data.get("traceback") or []
    if traceback_lines:
        lines.append("traceback:")
        for tb_line in traceback_lines[:30]:
            lines.append(tb_line.rstrip())

    return "\n".join(lines)


def _extract_history_failure_details(history_entry):
    """Extracts failure details from ComfyUI history status messages."""
    status = history_entry.get("status") or {}
    status_str = status.get("status_str")
    completed = status.get("completed")
    messages = status.get("messages") or []

    # Search from newest to oldest for the most relevant failure message.
    for message_type, payload in reversed(messages):
        if message_type in {"execution_error", "execution_interrupted"}:
            details = _format_comfy_execution_error(payload)
            return (
                f"status_str: {status_str}\n"
                f"completed: {completed}\n"
                f"message_type: {message_type}\n"
                f"{details}"
            )

    return (
        f"status_str: {status_str}\n"
        f"completed: {completed}\n"
        f"messages: {json.dumps(messages, indent=2)}"
    )


def upload_image_to_comfy(image_path, server_address):
    """Uploads an image to ComfyUI input folder via the /upload/image endpoint."""
    url = f"http://{server_address}/upload/image"
    base_filename = os.path.basename(image_path)

    import mimetypes

    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/png"  # default fallback

    print(f"📤 Uploading image '{base_filename}' to ComfyUI ({mime_type})...")
    with open(image_path, "rb") as f:
        files = {"image": (base_filename, f, mime_type)}
        data = {"overwrite": "true"}
        response = requests.post(url, files=files, data=data)

    if response.status_code == 200:
        result = response.json()
        server_filename = result.get("name")
        print(f"✅ Upload successful. Saved as: {server_filename}")
        return server_filename
    else:
        raise Exception(f"❌ Failed to upload image: {response.text}")


def upload_images_to_workflow(prompt_workflow, image_mappings, server_address):
    """Uploads multiple images and assigns each one to a specific LoadImage node."""
    for node_id, image_path in image_mappings.items():
        if not image_path:
            continue

        if node_id not in prompt_workflow:
            raise ValueError(
                f"❌ Specified image node ID '{node_id}' not found in workflow. "
                f"Found IDs: {list(prompt_workflow.keys())}"
            )

        server_filename = upload_image_to_comfy(image_path, server_address)
        prompt_workflow[node_id]["inputs"]["image"] = server_filename
        print(f"🖼️ Set input image of node {node_id} to '{server_filename}'")


def run_comfyui_workflow(
    workflow_file,
    output_file_path,
    prompt_modifications,
    output_node_id="3",
    input_image_path=None,
    input_image_node_id=None,
    input_image_mappings=None,
):
    def free_comfyui_memory():
        """Ask ComfyUI to unload models and release cached memory before a run."""
        url = f"http://{SERVER_ADDRESS}/free"
        payload = {"unload_models": True, "free_memory": True}
        try:
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                print("🧹 Requested ComfyUI to unload models and free memory.")
            else:
                print(
                    "⚠️ ComfyUI /free request returned "
                    f"HTTP {response.status_code}: {response.text}"
                )
        except Exception as exc:
            print(f"⚠️ Could not call ComfyUI /free endpoint: {exc}")

    # 1. Load the exported API JSON
    current_dir = Path(__file__).resolve().parent
    with open(
        current_dir / "workflow_files" / workflow_file, "r", encoding="utf-8"
    ) as f:
        prompt_workflow = json.load(f)

    # 1b. Upload either a specific set of input images or one image.
    if input_image_mappings:
        upload_images_to_workflow(prompt_workflow, input_image_mappings, SERVER_ADDRESS)
    elif input_image_path:
        server_filename = upload_image_to_comfy(input_image_path, SERVER_ADDRESS)
        if input_image_node_id:
            if input_image_node_id in prompt_workflow:
                prompt_workflow[input_image_node_id]["inputs"][
                    "image"
                ] = server_filename
                print(
                    f"Set input image of node {input_image_node_id} to"
                    f" '{server_filename}'"
                )
            else:
                raise ValueError(
                    f"❌ Specified image node ID '{input_image_node_id}' not found in"
                    f" workflow. Found IDs: {list(prompt_workflow.keys())}"
                )
        else:
            # Auto-detect LoadImage node
            found = False
            for node_id, node in prompt_workflow.items():
                if node.get("class_type") == "LoadImage":
                    node["inputs"]["image"] = server_filename
                    print(
                        f"🎯 Auto-detected 'LoadImage' node {node_id} and set to"
                        f" '{server_filename}'"
                    )
                    found = True
            if not found:
                raise ValueError(
                    "❌ No 'LoadImage' node found in the workflow to set the uploaded"
                    " image."
                )

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
        if req.status_code != 200:
            raise RuntimeError(
                f"❌ Failed to queue ComfyUI prompt. HTTP {req.status_code}: {req.text}"
            )

        payload = req.json()
        node_errors = payload.get("node_errors") or {}
        if node_errors:
            raise RuntimeError(
                "❌ ComfyUI prompt validation failed with node errors:\n"
                f"{json.dumps(node_errors, indent=2)}"
            )

        return payload

    def download_file(filename, subfolder, folder_type):
        """Downloads the file from the ComfyUI output directory."""
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        response = requests.get(f"http://{SERVER_ADDRESS}/view", params=params)
        if response.status_code == 200:
            source_ext = Path(filename).suffix.lower()
            target_ext = Path(output_file_path).suffix.lower()

            # ComfyUI TTS preview nodes commonly return FLAC; convert to WAV when requested.
            if target_ext == ".wav" and source_ext != ".wav":
                with tempfile.NamedTemporaryFile(
                    suffix=source_ext or ".bin", delete=False
                ) as tmp_input:
                    tmp_input.write(response.content)
                    tmp_input_path = tmp_input.name

                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", tmp_input_path, output_file_path],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    print(f"✅ Audio converted and saved to: {output_file_path}")
                except FileNotFoundError as exc:
                    raise RuntimeError(
                        "❌ ffmpeg is required to convert audio to WAV but was not found"
                        " on PATH."
                    ) from exc
                except subprocess.CalledProcessError as exc:
                    raise RuntimeError(
                        "❌ Failed to convert downloaded audio to WAV via ffmpeg.\n"
                        f"ffmpeg stderr: {exc.stderr}"
                    ) from exc
                finally:
                    try:
                        os.remove(tmp_input_path)
                    except OSError:
                        pass
            else:
                with open(output_file_path, "wb") as f:
                    f.write(response.content)
                print(f"✅ File successfully saved to: {output_file_path}")
        else:
            print(f"❌ Failed to download file. Status: {response.status_code}")

    def track_and_download():
        """Connects via WebSockets, tracks execution, and triggers the download."""
        # Establish WebSocket connection
        ws = websocket.WebSocket()
        ws.connect(f"ws://{SERVER_ADDRESS}/ws?clientId={CLIENT_ID}")
        ws.settimeout(5)

        execution_error_data = None
        prompt_id = None
        history = {}

        try:
            free_comfyui_memory()

            # Queue the workflow execution
            print("🚀 Submitting workflow to ComfyUI...")
            prompt_response = queue_prompt(prompt_workflow, CLIENT_ID)
            prompt_id = prompt_response.get("prompt_id")
            print(f"🎫 Prompt ID Queued: {prompt_id}")

            # Listen to server events
            while True:
                try:
                    out = ws.recv()
                except websocket.WebSocketTimeoutException:
                    # Some quick workflows may complete before we receive all
                    # websocket events; poll history as a fallback.
                    history_poll = requests.get(
                        f"http://{SERVER_ADDRESS}/history/{prompt_id}"
                    )
                    history_poll_entry = history_poll.json().get(prompt_id)
                    if history_poll_entry:
                        status = history_poll_entry.get("status") or {}
                        if status.get("completed") is True:
                            print(
                                "🏁 Execution complete (history poll). Fetching"
                                " metadata..."
                            )
                            break
                        if status.get("status_str") == "error":
                            execution_error_data = None
                            print(
                                "❌ ComfyUI execution error detected from history poll."
                            )
                            break
                    continue

                if not isinstance(out, str):
                    continue
                message = json.loads(out)

                msg_type = message.get("type")
                data = message.get("data", {})
                if data.get("prompt_id") != prompt_id:
                    continue

                # Track execution progress
                if msg_type == "executing":
                    data = message["data"]
                    if data["node"] is None:
                        print("🏁 Execution complete! Fetching metadata...")
                        break  # Total execution finished
                    print(f"⏳ Currently processing Node ID: {data['node']}")

                elif msg_type in {"execution_error", "execution_interrupted"}:
                    execution_error_data = data
                    print("❌ ComfyUI execution error received from WebSocket.")
                    break

            # Request historical outputs for this prompt to get the exact filename
            history_req = requests.get(f"http://{SERVER_ADDRESS}/history/{prompt_id}")
            history_entry = history_req.json().get(prompt_id, {})
            history = history_entry
            outputs = history.get("outputs", {})

            status = history.get("status") or {}
            status_str = status.get("status_str")
            completed = status.get("completed")

            if (
                execution_error_data is not None
                or status_str == "error"
                or completed is False
            ):
                websocket_details = _format_comfy_execution_error(execution_error_data)
                history_details = _extract_history_failure_details(history)
                raise RuntimeError(
                    "❌ ComfyUI graph execution failed.\n"
                    "WebSocket error details:\n"
                    f"{websocket_details}\n\n"
                    "History failure details:\n"
                    f"{history_details}"
                )

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
                    elif "audio" in node_output:
                        file_info = node_output["audio"][0]
                        break
                    elif "audios" in node_output:
                        file_info = node_output["audios"][0]
                        break

            if file_info:
                filename = file_info.get("filename")
                subfolder = file_info.get("subfolder", "")
                folder_type = file_info.get("type", "output")
                print(f"📦 Found video file: {filename}. Starting download...")
                download_file(filename, subfolder, folder_type)
            else:
                raise RuntimeError(
                    "❌ Workflow finished without downloadable file metadata.\n"
                    f"output_node_id: {output_node_id}\n"
                    f"available_output_nodes: {list(outputs.keys())}\n"
                    f"history_status: {json.dumps(status, indent=2)}"
                )
        finally:
            ws.close()

    track_and_download()

    free_comfyui_memory()


def generate_video_from_image(
    input_image_path,
    workflow_file="i2v_exported.json",
    output_file_path=OUTPUT_VIDEO_PATH,
    prompt_modifications=None,
    output_node_id="60",
):
    """Generates a video from an input image using ComfyUI."""
    if prompt_modifications is None:
        prompt_modifications = {}

    run_comfyui_workflow(
        workflow_file=workflow_file,
        output_file_path=output_file_path,
        prompt_modifications=prompt_modifications,
        output_node_id=output_node_id,
        input_image_path=input_image_path,
        input_image_node_id=None,  # Auto-detect LoadImage node
        input_image_mappings=None,
    )


def generate_image_from_prompt(
    prompt,
    output_file_path="generated_image.png",
):
    """Generates an image from a text prompt using ComfyUI."""

    workflow_file = "i_gen.json"

    prompt_modifications = {
        "6": lambda node: {**node, "inputs": {**node.get("inputs", {}), "text": prompt}}
    }

    output_node_id = "9"  # Node ID for the output image node

    run_comfyui_workflow(
        workflow_file=workflow_file,
        output_file_path=output_file_path,
        prompt_modifications=prompt_modifications,
        output_node_id=output_node_id,
        input_image_path=None,  # No input image for this workflow
        input_image_node_id=None,
        input_image_mappings=None,
    )


def generate_image_from_images_and_prompt(
    input_image_paths,
    prompt,
    workflow_file="i_edit_exported.json",
    output_file_path="generated_image.png",
):
    """Generates an image from 1-3 input images and a text prompt using ComfyUI."""
    if not (1 <= len(input_image_paths) <= 3):
        raise ValueError("❌ i_edit_exported.json requires 1 to 3 --image arguments.")

    load_node_ids = ["41", "74", "75"]
    image_input_keys = ["image1", "image2", "image3"]
    provided_count = len(input_image_paths)

    def _build_qwen_conditioning_node(node, node_prompt):
        inputs = {**node.get("inputs", {}), "prompt": node_prompt}

        # Keep only the image inputs that were provided for this run.
        for index, input_key in enumerate(image_input_keys):
            if index < provided_count:
                inputs[input_key] = [load_node_ids[index], 0]
            else:
                inputs.pop(input_key, None)

        return {**node, "inputs": inputs}

    prompt_modifications = {
        "68": lambda node: _build_qwen_conditioning_node(node, prompt),
        "69": lambda node: _build_qwen_conditioning_node(node, ""),
    }

    output_node_id = "9"
    input_image_mappings = {
        load_node_ids[index]: image_path
        for index, image_path in enumerate(input_image_paths)
    }

    run_comfyui_workflow(
        workflow_file=workflow_file,
        output_file_path=output_file_path,
        prompt_modifications=prompt_modifications,
        output_node_id=output_node_id,
        input_image_path=None,
        input_image_node_id=None,
        input_image_mappings=input_image_mappings,
    )


def generate_video_from_image_and_prompt(
    input_image_path, prompt, output_file_path="generated_video.mp4"
):
    """Generates a video from an input image and a text prompt using ComfyUI."""
    workflow_file = "i2v_exported.json"
    output_node_id = "60"

    prompt_modifications = {
        "100": lambda node: {
            **node,
            "inputs": {**node.get("inputs", {}), "positive_prompt": prompt},
        }
    }

    run_comfyui_workflow(
        workflow_file=workflow_file,
        output_file_path=output_file_path,
        prompt_modifications=prompt_modifications,
        output_node_id=output_node_id,
        input_image_path=input_image_path,  # Provide the input image for this workflow
        input_image_node_id="67",  # Auto-detect LoadImage node
        input_image_mappings=None,
    )


def generate_audio_from_prompt(
    prompt,
    output_file_path="generated_audio.wav",
):
    """Generates audio from text prompt using ComfyUI TTS workflow."""
    workflow_file = "tts_audio.json"

    # Node 65 is PrimitiveStringMultiline in tts_audio.json
    prompt_modifications = {
        "65": lambda node: {
            **node,
            "inputs": {**node.get("inputs", {}), "value": prompt},
        }
    }

    # Node 15 (PreviewAudio) stores downloadable audio metadata in history.
    output_node_id = "15"

    # output_file_path_temp = output_file_path.replace(
    #     ".wav", "_long_version.wav"
    # )  # Temporary file for initial download

    run_comfyui_workflow(
        workflow_file=workflow_file,
        output_file_path=output_file_path,
        prompt_modifications=prompt_modifications,
        output_node_id=output_node_id,
        input_image_path=None,
        input_image_node_id=None,
        input_image_mappings=None,
    )

    # # 1. Load the WAV file (returns audio data and sample rate)
    # audio_data, sample_rate = librosa.load(output_file_path_temp, sr=None)

    # # 2. Speed up the audio (e.g., 1.5x faster)
    # # Use a factor > 1.0 to speed up, < 1.0 to slow down
    # sped_up_audio = librosa.effects.time_stretch(audio_data, rate=1.2)

    # # 3. Save the modified audio
    # sf.write(output_file_path, sped_up_audio, sample_rate)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ComfyUI workflows.")
    parser.add_argument(
        "--workflow",
        type=str,
        default="i_edit_exported.json",
        help="Workflow JSON file name",
    )
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        help=(
            "Path to an input image. Repeat this flag 1-3 times for"
            " i_edit_exported.json."
        ),
    )
    parser.add_argument(
        "--prompt", type=str, default="", help="Prompt for the workflow"
    )
    parser.add_argument(
        "--output", type=str, default="generated_image.png", help="Output file path"
    )

    args = parser.parse_args()

    if args.workflow == "i_edit_exported.json":
        if not (1 <= len(args.image) <= 3):
            raise ValueError(
                "❌ i_edit_exported.json requires 1 to 3 --image arguments."
            )

        generate_image_from_images_and_prompt(
            input_image_paths=args.image,
            prompt=args.prompt,
            workflow_file=args.workflow,
            output_file_path=args.output,
        )
    elif args.workflow == "i2v_exported.json":
        if len(args.image) != 1:
            raise ValueError("❌ i2v_exported.json requires exactly 1 --image argument.")

        generate_video_from_image_and_prompt(
            input_image_path=args.image[0],
            prompt=args.prompt,
            output_file_path=args.output,
        )
    elif args.workflow == "tts_audio.json":
        if len(args.image) != 0:
            raise ValueError("❌ tts_audio.json does not accept --image arguments.")
        if not args.prompt.strip():
            raise ValueError("❌ tts_audio.json requires a non-empty --prompt.")

        generate_audio_from_prompt(
            prompt=args.prompt,
            output_file_path=args.output,
        )
    else:
        raise ValueError(
            f"❌ Unsupported workflow for this script entrypoint: {args.workflow}"
        )
