from prefect import task, flow
from dotenv import load_dotenv
import os 
from sql_utils import get_db, populate_towns, populate_weekends

@task 
def create_tables():
    from sqlalchemy import create_engine
    from tables import Base
    
    os.remove("data/local.db") if os.path.exists("data/local.db") else None

    engine = create_engine('sqlite:///data/local.db', echo=False) # echo=True shows SQL logs

    Base.metadata.create_all(engine)
    
    populate_weekends()
    populate_towns()

@flow(name="Weekend Short Generation Flow - Initialization")
def main_flow():
        
    load_dotenv()
    
    create_tables()

if __name__ == "__main__":
    main_flow()