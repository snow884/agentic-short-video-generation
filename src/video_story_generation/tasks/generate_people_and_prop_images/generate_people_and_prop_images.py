from prefect import task
from run_comfy_graph import generate_image_from_prompt

from sql_utils import get_db
from tables import PeopleAndProps
from tables import Videos as Video


@task(task_run_name="generate_script")
def main(video_id):

    session = next(get_db())

    video = session.query(Video).filter(Video.id == video_id).first()

    people_and_props_list = (
        session.query(PeopleAndProps)
        .filter(PeopleAndProps.video_id == video_id)
        .order_by(PeopleAndProps.id.asc())
    )

    if people_and_props_list.count() == 0:
        raise ValueError(f"No PeopleAndProps found for video_id {video_id}")

    # Run the ComfyUI workflow to generate the script
    for p_or_p in people_and_props_list:
        output_file_path = f"data/images/people_and_props_{p_or_p.video_id}_{p_or_p.id}_{p_or_p.name}.png"
        prompt = p_or_p.prompt + ", full body image"
        generate_image_from_prompt(
            prompt=prompt,
            output_file_path=output_file_path,
        )
        p_or_p.image_path = output_file_path
        session.commit()
