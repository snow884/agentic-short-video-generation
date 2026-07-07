import os
import time
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
        description=video.description[
            :2000
        ],  # Truncate description to first 2000 characters
        user="AmericaAIreacts",
        platforms=["instagram", "youtube", "x"],
    )

    request_id = response.get("request_id")

    status = client.get_status(request_id)

    while status.get("status") not in ["completed", "failed"]:
        status = client.get_status(request_id)
        logger.info(f"Upload status: {status}")
        time.sleep(10)

    results = status.get("results")

    for res in results:
        logger.info(
            f"Platform: {res.get('platform')}, Status: {res.get('status')}, URL:"
            f" {res.get('url')}"
        )

        if res.get("platform") == "instagram":
            logger.info(f"Instagram URL: {res.get('url')}")
            video.instagram_url = res.get("url")
            session.commit()

        if res.get("platform") == "youtube":
            logger.info(f"Youtube URL: {res.get('url')}")
            video.youtube_url = res.get("url")
            session.commit()

        # if res.get("platform") == "facebook":
        #     logger.info(f"Facebook URL: {res.get('url')}")
        #     video.facebook_url = res.get("url")
        #     session.commit()

        if res.get("platform") == "tiktok":
            logger.info(f"TikTok URL: {res.get('url')}")
            video.tiktok_url = res.get("url")
            session.commit()

    print(f"Upload status: {    status.get('status')}")

    response = client.upload_video(
        video_path=parent_dir / video.video_file_path,
        title=video.title + "\n\n" + video.description,
        user="AmericaAIreacts",
        platforms=["tiktok"],
    )

    request_id = response.get("request_id")

    status = client.get_status(request_id)

    while status.get("status") not in ["completed", "failed"]:
        status = client.get_status(request_id)
        logger.info(f"Upload status: {status}")
        time.sleep(10)

    results = status.get("results")

    for res in results:
        logger.info(
            f"Platform: {res.get('platform')}, Status: {res.get('status')}, URL:"
            f" {res.get('url')}"
        )

        if res.get("platform") == "instagram":
            logger.info(f"Instagram URL: {res.get('url')}")
            video.instagram_url = res.get("url")
            session.commit()

        if res.get("platform") == "youtube":
            logger.info(f"Youtube URL: {res.get('url')}")
            video.youtube_url = res.get("url")
            session.commit()

        # if res.get("platform") == "facebook":
        #     logger.info(f"Facebook URL: {res.get('url')}")
        #     video.facebook_url = res.get("url")
        #     session.commit()

        if res.get("platform") == "tiktok":
            logger.info(f"TikTok URL: {res.get('url')}")
            video.tiktok_url = res.get("url")
            session.commit()

    print(f"Upload status: {    status.get('status')}")
