from sqlalchemy.orm import Session

from sqlalchemy import create_engine

from tables import Base, Towns, Weekends

engine = create_engine('sqlite:///data/local.db', echo=False) # echo=True shows SQL logs

def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()
        
def create_tables():
        
    Base.metadata.create_all(engine) 
    

def populate_weekends():
    
    session = next(get_db())
    
    if session.query(Weekends).first():
        session.close()
        return
    
    # Example: Populate weekends with some dummy data
    weekends = [
        Weekends(date="2026-05-16")
    ]
    
    for weekend in weekends:
        session.add(weekend)
    
    session.commit()
    session.close()
    
def populate_towns():
    
    session = next(get_db())
    
    if session.query(Towns).first():
        session.close()
        return
    
    # Example: Populate towns with some dummy data
    towns = [
        Towns(name="Allentown", state="PA")
    ]
    
    for town in towns:
        session.add(town)
    
    session.commit()
    session.close()