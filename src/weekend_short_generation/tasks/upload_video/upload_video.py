import os
from pathlib import Path

from prefect import task
from prefect.logging import get_run_logger
from upload_post import UploadPostClient

from sql_utils import get_db
from tables import Video


@task(
    task_run_name="upload_video-{video_id}",
    # retries=3,
    # retry_delay_seconds=10,
)
def main(video_id):

    logger = get_run_logger()
    session = next(get_db())

    video = session.query(Video).filter(Video.id == video_id).first()

    logger = get_run_logger()
    session = next(get_db())

    parent_dir = Path(__file__).parent.parent.parent.parent.parent

    client = UploadPostClient(api_key=os.environ.get("UPLOAD_POST_API_KEY"))

    response = client.upload_video(
        video_path=parent_dir / video.video_file_path,
        title=video.title,
        description=video.description,
        user="AmericaAIreacts",
        platforms=["instagram", "youtube"],
    )

    print(f"Upload response: {response}")
