import os
from pathlib import Path

from prefect import task
from prefect.logging import get_run_logger
from pydantic import BaseModel

from research_agent import run_agent_sync
from sql_utils import get_db
from tables import Video


class SuccessResponse(BaseModel):

    success: bool


@task(
    task_run_name="upload_video-{video_id}",
    retries=3,
    retry_delay_seconds=10,
)
def main(video_id):

    logger = get_run_logger()
    session = next(get_db())

    video = session.query(Video).filter(Video.id == video_id).first()

    logger = get_run_logger()
    session = next(get_db())

    success = run_agent_sync(
        user_prompt_params={
            "video_path": video.video_file_path,
            "description": video.description,
        },
        system_prompt_params={},
        ReturnClass=SuccessResponse,
        prompt_dir=Path(__file__).parent.resolve(),
        extra_tools=[],
        extra_cookie_file=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "www.tiktok.com_cookies.txt"
        ),
    )

    return success
