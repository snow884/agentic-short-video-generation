
from tables import Base


if __name__ == "__main__":
    
    from dotenv import load_dotenv
    from sqlalchemy import create_engine


    engine = create_engine('sqlite:///data/local.db', echo=False) # echo=True shows SQL logs

    load_dotenv()

    def create_tables():
        
        Base.metadata.create_all(engine) 

    create_tables()