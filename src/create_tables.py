
import os

from tables import Base
from sql_utils import get_db, populate_towns, populate_weekends
from pathlib import Path

if __name__ == "__main__":
    
    from dotenv import load_dotenv
    from sqlalchemy import create_engine

    os.remove("data/local.db") if os.path.exists("data/local.db") else None

    engine = create_engine('sqlite:///data/local.db', echo=False) # echo=True shows SQL logs

    load_dotenv()

    def create_tables():
        
        Base.metadata.create_all(engine) 

    create_tables()
    
    populate_weekends()
    populate_towns()