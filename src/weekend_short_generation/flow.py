from dotenv import load_dotenv
from prefect import flow, task
from prefect.logging import get_run_logger
from tasks.event_research_agent.event_research_agent import (
    main as event_research_agent_main,
)
from tasks.video_description_generator.video_description_generator import (
    main as video_description_generator_agent_main,
)
from tasks.video_generator.video_generator import main as video_generator_agent_main
from tasks.video_parts_generator.video_parts_generator import (
    main as video_parts_generator_agent_main,
)
from tasks.video_script_generator.video_script_generator import (
    main as video_script_generator_agent_main,
)

from sql_utils import get_db
from tables import Towns, Video, Weekends


@task(task_run_name="create_video-{weekend_id}-{town_id}")
def create_video(weekend_id, town_id):

    session = next(get_db())

    video = Video(
        town_id=town_id,
        weekend_id=weekend_id,
        video_file_path="",
        audio_file_path="",
        description="",
        title="Events in {town_name} on {weekend_date}".format(
            town_name=session.query(Towns).filter(Towns.id == town_id).first().name,
            weekend_date=session.query(Weekends)
            .filter(Weekends.id == weekend_id)
            .first()
            .date,
        ),
    )
    session.add(video)
    session.commit()

    return video.id


@flow(name="Weekend Short Generation Flow", log_prints=True)
def main_flow(weekend_id, town_id_list):

    logger = get_run_logger()

    load_dotenv()

    for town_id in town_id_list:

        video_id = create_video(weekend_id, town_id)

        # video_id = 1

        logger.info(f"Processing town_id: {town_id} for weekend_id: {weekend_id}")

        event_id_list = event_research_agent_main(
            town_id=town_id, weekend_id=weekend_id
        )

        video_script_generator_agent_main(video_id)

        video_parts_generator_agent_main(video_id)

        video_generator_agent_main(video_id)

        video_description_generator_agent_main(video_id)


if __name__ == "__main__":
    main_flow(weekend_id=1, town_id_list=[2, 3, 4, 5, 6, 7, 8, 9, 10])
