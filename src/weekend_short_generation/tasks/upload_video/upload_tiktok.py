import os

from prefect import task
from tiktok_uploader.upload import TikTokUploader

from sql_utils import get_db
from tables import Video


@task(
    task_run_name="upload_tiktok-{video_id}",
    retries=3,
    retry_delay_seconds=10,
)
def main(video_id):
    session = next(get_db())

    video = session.query(Video).filter(Video.id == video_id).first()

    video_file_path = video.video_file_path

    # get current python file path
    current_file_path = __file__
    # get parent directory of current file
    parent_dir = os.path.dirname(current_file_path)

    uploader = TikTokUploader(
        cookies=parent_dir + "/www.tiktok.com_cookies.txt",
        headless=True,
        browser="chrome",
    )
    uploader.upload_video(video_file_path, description=video.description)

    print("Video upload triggered successfully!")


if __name__ == "__main__":
    main(video_id=1)
