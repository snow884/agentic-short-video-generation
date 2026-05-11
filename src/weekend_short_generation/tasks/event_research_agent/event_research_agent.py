
from dataclasses import asdict

import nest_asyncio

from research_agent import run_agent_sync


from sql_utils import get_db, populate_towns, populate_weekends
from tables import Base, Events, Towns, Weekends

from pathlib import Path
from tables import EventList
from prefect import flow, task

def populate_db_with_events(event_list: EventList, town_id: int, weekend_id: int):

    session = next(get_db())
    
    event_id_list = []
    
    for new_event in event_list.events:
        print("Adding the event ", new_event.event_name)
        new_event_sql = Events(**new_event.__dict__)
        new_event_sql.town_id = town_id
        new_event_sql.weekend_id = weekend_id
        session.add(new_event_sql)
        event_id_list.append(new_event_sql.id)
        
    session.commit()

    session.close()
    
    return event_id_list

@task
def main(town_id=0, weekend_id=0):
    session = next(get_db())
    
    w = session.query(Weekends).filter(Weekends.id==weekend_id).first()
    t = session.query(Towns).filter(Towns.id==town_id).first()
    
    event_list = run_agent_sync(user_prompt_params={"town_name": t.name, "town_state": t.state, "weekend_date": w.date}, ReturnClass=EventList, prompt_dir=Path(__file__).parent.resolve())
    event_id_list = populate_db_with_events(event_list, town_id=town_id, weekend_id=weekend_id)
    
    return event_id_list

if __name__ == "__main__":
    from dotenv import load_dotenv
    from sqlalchemy import create_engine


    engine = create_engine('sqlite:///data/local.db', echo=False) # echo=True shows SQL logs

    load_dotenv()

    def create_tables():
            
        Base.metadata.create_all(engine) 

    create_tables()

    main(town_id=1, weekend_id=1)