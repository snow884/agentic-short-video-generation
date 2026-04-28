
from dataclasses import asdict


import nest_asyncio

from research_agent import run_agent_sync


from sql_utils import get_db
from tables import Events, Towns, Weekends

from pathlib import Path
from tables import EventList



def populate_db_with_events(event_list: EventList, town_id: int, weekend_id: int):

    session = next(get_db())
    
    for new_event in event_list.events:
        print("Adding the event ", new_event.event_name)
        new_event_sql = Events(**asdict(new_event))
        new_event_sql.town_id = town_id
        new_event_sql.weekend_id = weekend_id
        session.add(new_event_sql)
        
    session.commit()
    
    session.close()


def main(town_id=0, weekend_id=0):
    session = next(get_db())
    
    w = session.query(Weekends).filter(Weekends.id==weekend_id).first()
    t = session.query(Towns).filter(Towns.id==town_id).first()
    
    event_list = run_agent_sync(user_prompt_params={"town_name": t.name, "town_state": t.state, "weekend_date": w.date}, ReturnClass=EventList, prompt_dir=Path(__file__).parent.resolve())
    populate_db_with_events(event_list, town_id=town_id, weekend_id=weekend_id)

    
if __name__ == "__main__":
    main()