import base64
import json
import os

import cv2
import ollama
from prefect import get_run_logger

from sql_utils import get_db
from tables import Videos, VideoSegments


def get_video_frames(video_id: str, timestamp: int) -> str:
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
        if (frame_count / fps >= timestamp) and (
            frame_count / fps <= timestamp + 5
        ):  # Stop after 5 seconds from the timestamp

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
        frames_base64.append(base64.b64encode(buffer).decode("utf-8"))

    return frames_base64


def main(video_id: str) -> str:
    session = next(get_db())
    logger = get_run_logger()

    video = session.query(Videos).filter(Videos.id == video_id).first()
    if video is None:
        raise ValueError(f"No Video found for video_id {video_id}")

    script_list = (
        session.query(VideoSegments)
        .filter(VideoSegments.video_id == video_id)
        .order_by(VideoSegments.timestamp.asc())
        .all()
    )

    for script in script_list:
        logger.info(
            f"Segment ID: {script.id}, Timestamp: {script.timestamp}, Narrator Script:"
            f" {script.narrator_script}, Start Image Prompt:"
            f" {script.start_image_prompt}, Video Prompt: {script.video_prompt}, Start"
            " Image People and Props Names:"
            f" {script.start_image_people_and_props_names}"
        )

        script_json = json.dumps(
            {
                "start_image_prompt": script.start_image_prompt,
                "video_prompt": script.video_prompt,
                "timestamp": script.timestamp,
            }
        )

        frames = get_video_frames(video_id, timestamp=script.timestamp)

        sys_prompt = f"""
                    You are a helpful assistant that improves scripts containing image prompts used to generate AI generated videos.
                    
                    In the pipeline that generates video, start_image_prompt is first used to generate an image and then the resulting 
                    image plus a video_prompt is used to generate a video. 
                    
                    You are given a series of images that are frames extracted from the video. You are also given a JSON script that contains the start image prompt 
                    and video prompt.
                    
                    The AI image or video generator sometimes produces results that do not fully match the prompts. Your job is to identify any issues 
                    in the images that are not matching the prompts and improve the prompts to generate correct images by making them more descriptive or removing vague working.
                    
                    # JSON Schema Requirements
                    Output ONLY pure JSON matching this exact structure. Do not include any reasoning or details. just pure JSON. 
                    Return your response in the format matching the script, with the same keys, but with improved prompts. Do not include any reasoning as a part of the new prompt. Just a new prompt. 
                    If you cannot improve a prompt, return the original prompt.
                    """

        user_prompt = f"""
                    Please improve the JSON script for the video.
                    
                    I am providing video frames extracted from the video. 
                    
                    Here is the script for the video:
                    {script_json}
                    
                    """

        print(f"sys_prompt: {sys_prompt}")
        print(f"user_prompt: {user_prompt}")

        res = ollama.chat(
            model=os.getenv("RESEARCH_AGENT_MODEL", "qwen3.6:27b-q4_K_M"),
            think=False,
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

        content_json = json.loads(res["message"]["content"])

        changes_made = False

        if script.start_image_prompt != content_json["start_image_prompt"]:
            logger.info(
                f"Old segment: {script.start_image_prompt} -->"
                f" {content_json['start_image_prompt']}"
            )
            script.start_image_prompt = content_json["start_image_prompt"]
            changes_made = True

        if script.video_prompt != content_json["video_prompt"]:
            logger.info(
                f"Old segment: {script.video_prompt} --> {content_json['video_prompt']}"
            )
            script.video_prompt = content_json["video_prompt"]
            changes_made = True

        if changes_made:
            raise ValueError(
                f"Changes were made to the script for segment ID {script.id}. Please"
                " review the changes and re-run the pipeline."
            )

    print(f"content_json: {content_json}")
