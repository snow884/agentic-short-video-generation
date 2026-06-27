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

    uploader = TikTokUploader(cookies="www.tiktok.com_cookies.txt")
    uploader.upload_video(video_file_path, description=video.description)

    print("Video upload triggered successfully!")


if __name__ == "__main__":
    main(video_id=1)
