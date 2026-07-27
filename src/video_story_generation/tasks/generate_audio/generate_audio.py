from prefect import task
from run_comfy_graph import generate_audio_from_prompt

from sql_utils import get_db
from tables import Videos as Video
from tables import VideoSegments


@task(task_run_name="generate_audio")
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

        audio_path = f"data/audio/segment_{video_id}_{segment.id}.wav"

        generate_audio_from_prompt(
            prompt=segment.video_prompt,
            output_file_path=audio_path,
        )

        segment.audio_file_path = audio_path

        session.commit()
