import os

import whisper
from prefect import task
from prefect.logging import get_run_logger
from whisper.utils import get_writer

from sql_utils import get_db
from tables import Video


@task(
    task_run_name="subtitle_gen-{video_id}",
    retries=3,
    retry_delay_seconds=10,
)
def main(video_id=0):

    logger = get_run_logger()
    session = next(get_db())

    video = session.query(Video).filter(Video.id == video_id).first()

    audio_file_path = video.audio_file_path

    if not audio_file_path:
        parent_dir = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
            )
        )
        audio_file_path = os.path.join(
            parent_dir, f"data/video/sad_talker_input/combined_audio{video.id}.wav"
        )

    logger.info(
        f"Generating subtitles for video_id: {video_id} using audio file:"
        f" {audio_file_path}"
    )

    model = whisper.load_model(
        "base"
    )  # Use 'small', 'medium', or 'large' for better accuracy
    result = model.transcribe(audio_file_path)

    # Save as SRT
    logger.info(
        f"Transcription completed for video_id: {video_id}. Saving subtitles to SRT"
        " file."
    )
    writer = get_writer("srt", "data/video/")
    writer(result, audio_file_path)

    logger.info(f"Subtitles saved for video_id: {video_id}. Updating database record.")
    video.subtitle_file_path = audio_file_path.replace(".mp3", ".srt").replace(
        ".wav", ".srt"
    )
    session.commit()


if __name__ == "__main__":
    print(
        check_events(
            events_list=5
            * [
                {
                    "event_name": "Test Event",
                    "time": "afasdfda",
                    "description": "This is a test event.",
                    "location_address": "123 Main St, City, ST 12345",
                    "date": "2026-05-1ada6",
                }
            ]
        )
    )
