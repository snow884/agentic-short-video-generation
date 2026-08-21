import base64
import json
import os

import cv2
import ollama
from prefect import get_run_logger

from sql_utils import get_db
from tables import Videos, VideoSegments


def get_video_frames(video_id: str) -> str:
    """
    Open video and extract a frame every 1s

    Args:
        video_id (str): _description_

    Raises:
        ValueError: _description_

    Returns:
        str: _description_
    """

    logger = get_run_logger()
    session = next(get_db())

    video = session.query(Videos).filter(Videos.id == video_id).first()
    if video is None:
        raise ValueError(f"No Video found for video_id {video_id}")

    open_video_path = video.file_path

    logger.info(f"Opening video at path: {open_video_path}")

    cap = cv2.VideoCapture(open_video_path)
    frames = []
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(fps)  # Extract a frame every 1 second
    frame_count = 0
    while cap.isOpened():

        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % frame_interval == 0:
            logger.info(f"Reading frame {frame_count} from video...")
            frames.append(frame)
        frame_count += 1
    cap.release()

    # compress images to be less than 1kB
    quality = 50
    scale = 1.0
    target_size_bytes = 1024 * 3  # 1kB

    frames_base64 = []

    for frame in frames:
        img = frame
        while True:
            # Resize image if quality reduction is not enough
            if scale < 1.0:
                h, w = img.shape[:2]
                current_img = cv2.resize(img, (int(w * scale), int(h * scale)))
            else:
                current_img = img

            # Encode to JPEG memory buffer
            success, encoded = cv2.imencode(
                ".jpg", current_img, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            )
            if not success:
                raise ValueError("Encoding failed")

            # Check size in bytes
            size_bytes = len(encoded.tobytes())

            if size_bytes < target_size_bytes:
                break

            # Adjust parameters
            if quality > 10:
                quality -= 5
            else:
                scale -= 0.1
                quality = 50  # Reset quality for smaller dimensions
                if scale < 0.1:
                    raise ValueError(
                        "Image cannot be compressed below 1kB without losing all data."
                    )
            logger.info(
                f"Frame {frame_count}: Compressed image size: {size_bytes} bytes,"
                f" quality: {quality}, scale: {scale}"
            )

        # encode frame as to base64

        _, buffer = cv2.imencode(".jpg", current_img)
        frames_base64.append(
            "data:image/jpeg;base64," + base64.b64encode(buffer).decode("utf-8")
        )

    return frames_base64


def main(video_id: str) -> str:
    session = next(get_db())

    video = session.query(Videos).filter(Videos.id == video_id).first()
    if video is None:
        raise ValueError(f"No Video found for video_id {video_id}")

    script_list = (
        session.query(VideoSegments)
        .filter(VideoSegments.video_id == video_id)
        .order_by(VideoSegments.timestamp.asc())
        .all()
    )

    script_json = json.dumps(
        [
            {
                "narrator_script": script.narrator_script,
                "start_image_prompt": script.start_image_prompt,
                "video_prompt": script.video_prompt,
                "timestamp": script.timestamp,
                "start_image_people_and_props_names": script.start_image_people_and_props_names,
            }
            for script in script_list
        ]
    )

    frames = get_video_frames(video_id)

    sys_prompt = f"""
                You are a helpful assistant that provides improvements on prompts used to generate AI generated videos.
                
                Image prompt is first used to generate an image and then the image plus a video prompt is used to generate a video. 
                
                Return your response in the format matching the script_json, with the same keys, but with improved prompts. If you cannot improve a prompt, return the original prompt.
                
                Example response:
                [
                    {{
                        "narrator_script": "The narrator script for the segment.",
                        "start_image_prompt": "The improved start image prompt for the segment.",
                        "video_prompt": "The improved video prompt for the segment.",
                        "timestamp": 0,
                        "start_image_people_and_props_names": "The names of the people and props in the start image for the segment."
                    }},
                    {{
                        "narrator_script": "The narrator script for the segment.",
                        "start_image_prompt": "The improved start image prompt for the segment.",
                        "video_prompt": "The improved video prompt for the segment.",
                        "timestamp": 1,
                        "start_image_people_and_props_names": "The names of the people and props in the start image for the segment."
                    }}
                ]
                """

    user_prompt = f"""
                Please improve the JSON script for the video '{video.name}'.
                
                I am providing video frames extracted from the video to help you understand the context of the video. The frames are provided as base64 encoded images in a list. Please use these frames to inform your improvements to the script.
                
                Here is the script for the video:
                {script_json}
                
                """

    print(f"sys_prompt: {sys_prompt}")
    print(f"user_prompt: {user_prompt}")

    res = ollama.chat(
        model=os.getenv("RESEARCH_AGENT_MODEL", "qwen3.6:27b-q4_K_M"),
        think=True,
        format="json",
        messages=[
            {
                "role": "system",
                "content": sys_prompt,
            },
            {"role": "user", "content": user_prompt, "images": frames},
        ],
    )
    print(f"res: {res}")

    res = json.loads(res)
