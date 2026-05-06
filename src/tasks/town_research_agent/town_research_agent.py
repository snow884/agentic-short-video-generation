
from dataclasses import asdict
import mimetypes


import nest_asyncio

from research_agent import run_agent_sync


from sql_utils import get_db
from tables import Image,Events, Towns, Weekends

from pathlib import Path
from tables import TownsSchema, TownsList

import requests
import hashlib

def populate_db_with_towns(Town_list: TownsList):

    session = next(get_db())
    
    for new_Town in Town_list.towns:
        print("Adding the Town " + new_Town.name + " - " + new_Town.description)

        new_Town_sql = Towns(**new_Town.__dict__)
        session.add(new_Town_sql)
            
    session.commit()
    
    session.close()


def main():

    user_prompt_params = {
        "country_name":'US',
        "population_range":'1000-15000', 
    }

    Town_list = run_agent_sync(user_prompt_params=user_prompt_params, ReturnClass=TownsList, prompt_dir=Path(__file__).parent.resolve())
    print("Received Town list: ", Town_list  )
    populate_db_with_towns(Town_list)
    
    
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()