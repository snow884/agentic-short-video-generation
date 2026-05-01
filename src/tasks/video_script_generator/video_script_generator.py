
from dataclasses import asdict
import json


import nest_asyncio

from research_agent import run_agent_sync


from sql_utils import get_db, populate_towns, populate_weekends
from tables import Base, Events, Media, Towns, Weekends

from pathlib import Path
from tables import VideoSegmentsList

from llm import chat_ollama_with_structured_output


def populate_db_with_events(segments_list: VideoSegmentsList, event_id: int, weekend_id: int):

    session = next(get_db())
    
    for segment in segments_list.video_segments:
        print("Adding the segment ", segment.event_name)
        new_event_sql = Events(**asdict(segment))
        new_event_sql.town_id = town_id
        new_event_sql.weekend_id = weekend_id
        session.add(new_event_sql)
        
    session.commit()

    session.close()


def main(weekend_id=0, town_id=0):
    session = next(get_db())
    
    events = session.query(Events).filter(Events.weekend_id==weekend_id, Events.town_id==town_id).all()
    media = session.query(Media).join(Events).filter(Media.event_id.in_([event.id for event in events])).all()
    
    if not events:
        print("No events found for the given weekend and town.")
        return

    w = session.query(Weekends).filter(Weekends.id==weekend_id).first()
    t = session.query(Towns).filter(Towns.id==town_id).first()
    
    chat_ollama_with_structured_output(
        user_prompt_params={"town_name": t.name, "state": t.state, "weekend_date": w.date, "event_list":json.dumps([e._asdict() for e in events]), "media_list": json.dumps([m._asdict() for m in media])  },
        system_prompt_params={}, 
        return_class=VideoSegmentsList, 
        prompt_dir=Path(__file__).parent.resolve()
    )

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main(town_id=1, weekend_id=1)