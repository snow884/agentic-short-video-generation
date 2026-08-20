import base64
import json
import os

import cv2 as cv
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

    open_video_path = video.video_file_path
    logger.info(f"Opening video at path: {open_video_path}")

    cap = cv.VideoCapture(open_video_path)
    frames = []
    fps = cap.get(cv.CAP_PROP_FPS)
    frame_interval = int(fps)  # Extract a frame every 1 second
    frame_count = 0
    while cap.isOpened():
        logger.info(f"Reading frame {frame_count} from video...")
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % frame_interval == 0:
            frames.append(frame)
        frame_count += 1
    cap.release()

    # encode frame as to base64

    frames = [
        base64.b64encode(cv.imencode(".jpg", frame)[1]).tobytes().decode("utf-8")
        for frame in frames
    ]

    return frames


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

    frames_json = json.dumps(get_video_frames(video_id))

    ollama.chat(
        model=os.getenv("RESEARCH_AGENT_MODEL", "qwen3.6:27b-q4_K_M"),
        messages=[
            {
                "role": "system",
                "content": """
                You are a helpful assistant that provides improvements on prompts used to generate AI generated videos.
                
                Image prompt is first used to generate an image and then the image plus a video prompt is used to generate a video. 
                
                Return your response in the format matching the script_json, with the same keys, but with improved prompts. If you cannot improve a prompt, return the original prompt.
                """,
            },
            {
                "role": "user",
                "content": f"""
                Please improve the prompts for a video.
                
                Here is the script for the video:
                {script_json}
                
                Here are the frames from the video taken every 1 second:
                {frames_json}
                """,
            },
        ],
    )
