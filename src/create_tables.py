def main(town_id=0, weekend_id=0):
    session = next(get_db())
    
    w = session.query(Weekends).filter(Weekends.id==weekend_id).first()
    t = session.query(Towns).filter(Towns.id==town_id).first()
    
    event_list = run_agent_sync(user_prompt_params={"town_name": t.name, "town_state": t.state, "weekend_date": w.date}, ReturnClass=EventList, prompt_dir=Path(__file__).parent.resolve())
    populate_db_with_events(event_list, town_id=town_id, weekend_id=weekend_id)

if __name__ == "__main__":
    from dotenv import load_dotenv
    from sqlalchemy import create_engine


    engine = create_engine('sqlite:///data/local.db', echo=False) # echo=True shows SQL logs

    load_dotenv()

    def create_tables():
            
        Base.metadata.create_all(engine) 

    create_tables()