from prefect import task
from run_comfy_graph import generate_image_from_images_and_prompt

from sql_utils import get_db
from tables import PeopleAndProps
from tables import Videos as Video
from tables import VideoSegments


@task(task_run_name="generate_start_stop_images")
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

        start_image_people_and_props_names = segment.start_image_people_and_props_names

        image_paths = []

        name_to_image_map = {}

        for i, name in enumerate(start_image_people_and_props_names.split(",")):
            p_or_p = (
                session.query(PeopleAndProps)
                .filter(
                    PeopleAndProps.video_id == video_id,
                    PeopleAndProps.name == name.strip(),
                )
                .first()
            )
            if p_or_p is None:
                raise ValueError(
                    f"No PeopleAndProps found for video_id {video_id} and name {name}"
                )

            image_paths = image_paths + [p_or_p.image_path]
            name_to_image_map[name.strip()] = i

        output_file_path = (
            f"data/images/people_and_props_{segment.video_id}_{segment.id}_start.png"
        )

        prompt = segment.start_image_prompt

        for name in start_image_people_and_props_names.split(","):
            prompt = prompt.replace(
                name.strip(),
                f"{name.strip()} (from Image {name_to_image_map[name.strip()]})",
            )

        prompt = (
            prompt + ", match identities, bodies and faces from input images exactly."
        )

        generate_image_from_images_and_prompt(
            input_image_paths=image_paths,
            prompt=prompt,
            output_file_path=output_file_path,
        )

        segment.start_image_path = output_file_path

        session.commit()
