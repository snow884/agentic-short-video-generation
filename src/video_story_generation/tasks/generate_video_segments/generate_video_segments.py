from prefect import task
from run_comfy_graph import generate_video_from_image_and_prompt
from utils import generate_slug

from sql_utils import get_db
from tables import Videos as Video
from tables import VideoSegments


@task(task_run_name="generate_video_segments")
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
    for segment in segments:

        video_path = (
            f"data/video/segment_{segment.id}_{generate_slug(str(segment.id))}.mp4"
        )

        generate_video_from_image_and_prompt(
            input_image_path=segment.start_image_path,
            prompt=segment.video_prompt,
            output_file_path=video_path,
        )

        segment.video_path = video_path

        session.commit()
