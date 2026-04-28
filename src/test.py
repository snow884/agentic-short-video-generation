import tasks.event_research_agent.event_research_agent as event_research_agent

from tables import Base
from sqlalchemy import create_engine

from sql_utils import populate_towns, populate_weekends

from dotenv import load_dotenv

engine = create_engine('sqlite:///local.db', echo=False) # echo=True shows SQL logs

load_dotenv()

def create_tables():
        
    Base.metadata.create_all(engine) 

create_tables()
populate_weekends()
populate_towns()

event_research_agent.main(town_id=1, weekend_id=1)