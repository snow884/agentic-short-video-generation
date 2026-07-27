import hashlib
import os
from time import time

from prefect import task

from sql_utils import get_db
from tables import Videos as Video
from tables import VideoSegments

# Must be set BEFORE importing moviepy
os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

import hashlib
import time

from moviepy import VideoFileClip, concatenate_videoclips
from moviepy.editor import AudioFileClip, concatenate_audioclips
from moviepy.video.fx import MultiplySpeed
from prefect import task


@task(task_run_name="generate_full_video")
def main(video_id):

    session = next(get_db())

    video = session.query(Video).filter(Video.id == video_id).first()
    if video is None:
        raise ValueError(f"No Video found for video_id {video_id}")

    segments = (
        session.query(VideoSegments)
        .filter(VideoSegments.video_id == video_id)
        .order_by(VideoSegments.timestamp.asc())
    )

    if segments.count() == 0:
        raise ValueError(f"No Segments found for video_id {video_id}")

    # Run the ComfyUI workflow to generate the script

    combined_video = None
    combined_audio = None

    for segment in segments:

        # image = session.query(Image).filter(Image.id == segment.Image_id).first()

        print(
            f"Segment ID: {segment.id}, Audio Path: {segment.audio_file_path}, Video"
            f" Path: {segment.video_path}"
        )

        sound = AudioFileClip(segment.audio_file_path)

        duration = sound.duration

        combined_audio = (
            sound
            if combined_audio is None
            else concatenate_audioclips([combined_audio, sound])
        )

        clip = VideoFileClip(segment.video_path)

        slowdown_ratio = clip.duration / duration

        clip = clip.with_effects([MultiplySpeed(slowdown_ratio)]).with_end(duration)

        if combined_video is None:
            combined_video = clip
        else:
            combined_video = concatenate_videoclips(
                [
                    combined_video,
                    clip,
                ],
                method="compose",
            )

    final_video = combined_video.with_audio(combined_audio)

    # 1. Get the current Unix timestamp
    timestamp = str(time.time())

    # 2. Encode to bytes and create SHA-256 hash
    hash_object = hashlib.sha256(timestamp.encode("utf-8"))

    # 3. Get the hexadecimal representation
    hex_dig = hash_object.hexdigest()
    slug = hex_dig[0:5]  # You can take the first 10 characters for a shorter slug

    video.video_file_path = f"data/video/video_{video_id}_{slug}.mp4"

    final_video.write_videofile(
        video.video_file_path,
        codec="h264_nvenc",
        audio_codec="aac",
        ffmpeg_params=[
            "-preset",
            "p4",  # Use NVIDIA-specific preset (p1-p7)
            "-tune",
            "hq",  # Optional: high quality tuning
        ],
        threads=32,
        fps=24,
    )

    session.commit()
