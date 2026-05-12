from prefect import task, flow
from tasks.event_research_agent.event_research_agent import main as event_research_agent_main
from tasks.image_research_agent.image_research_agent import main as image_research_agent_main
from tasks.video_script_generator.video_script_generator import main as video_script_generator_agent_main
from tasks.video_generator.video_generator import main as video_generator_agent_main
from prefect.logging import get_run_logger

from dotenv import load_dotenv

@flow(name="Weekend Short Generation Flow", log_prints=True)
def main_flow(weekend_id, town_id):
    
    logger = get_run_logger()
    
    load_dotenv()
    
    event_id_list = event_research_agent_main(town_id=town_id, weekend_id=weekend_id)
    
    for event_id in event_id_list:
        logger.info(f"Processing event_id: {event_id}")
        image_research_agent_main(event_id=event_id)
        
    video_script_generator_agent_main(weekend_id=weekend_id, town_id=town_id)
    
    video_generator_agent_main(weekend_id=weekend_id, town_id=town_id)

if __name__ == "__main__":
    main_flow(weekend_id=1, town_id=6)