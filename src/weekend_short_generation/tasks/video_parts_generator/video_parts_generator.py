import json
import os

from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

import requests
from prefect import task
from pydub import AudioSegment

from sql_utils import get_db
from tables import Events, Towns, Video, VideoSegments, Weekends

VID_HEIGHT = int(1920 / 2)
VID_WIDTH = int(1080 / 2)


@task(task_run_name="video_parts_generator-{weekend_id}-{town_id}")
def main(weekend_id=1, town_id=1):
    session = next(get_db())

    events = (
        session.query(Events)
        .filter(Events.weekend_id == weekend_id, Events.town_id == town_id)
        .all()
    )

    w = session.query(Weekends).filter(Weekends.id == weekend_id).first()
    t = session.query(Towns).filter(Towns.id == town_id).first()

    video_segments = (
        session.query(VideoSegments)
        .filter(VideoSegments.event_id.in_([e.id for e in events]))
        .order_by(VideoSegments.timestamp)
        .all()
    )

    video = (
        session.query(Video)
        .filter(Video.weekend_id == weekend_id, Video.town_id == town_id)
        .first()
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

    video.sad_talker_video_path = video_path
    session.commit()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    session = next(get_db())
    for e in session.query(Events).all():
        print(e.id, e.event_name)

        main(weekend_id=e.weekend_id, town_id=e.town_id)
