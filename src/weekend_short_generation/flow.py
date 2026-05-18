from dotenv import load_dotenv
from prefect import flow
from prefect.logging import get_run_logger
from tasks.event_research_agent.event_research_agent import (
    main as event_research_agent_main,
)
from tasks.video_generator.video_generator import main as video_generator_agent_main
from tasks.video_parts_generator.video_parts_generator import (
    main as video_parts_generator_agent_main,
)
from tasks.video_script_generator.video_script_generator import (
    main as video_script_generator_agent_main,
)


@flow(name="Weekend Short Generation Flow", log_prints=True)
def main_flow(weekend_id, town_id_list):

    logger = get_run_logger()

    load_dotenv()

    for town_id in town_id_list:
        logger.info(f"Processing town_id: {town_id} for weekend_id: {weekend_id}")

        event_id_list = event_research_agent_main(
            town_id=town_id, weekend_id=weekend_id
        )

        video_script_generator_agent_main(weekend_id=weekend_id, town_id=town_id)

        video_parts_generator_agent_main(weekend_id=weekend_id, town_id=town_id)

        video_generator_agent_main(weekend_id=weekend_id, town_id=town_id)


if __name__ == "__main__":
    main_flow(weekend_id=1, town_id_list=[2, 3, 4, 5])
