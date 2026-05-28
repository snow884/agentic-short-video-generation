from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tables import Base, Towns, Weekends

engine = create_engine(
    "sqlite:///data/local.db", echo=False
)  # echo=True shows SQL logs


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
    weekends = [Weekends(date="2026-05-30")]

    for weekend in weekends:
        session.add(weekend)

    session.commit()
    session.close()


def populate_towns():

    session = next(get_db())

    if session.query(Towns).first():
        session.close()
        return

    raw_data = """1,New York City,NY,0,0.0%
2,Las Vegas,NV,0,0.0%
3,Orlando,FL,0,0.0%
4,Chicago,IL,0,0.0%
5,Los Angeles,CA,0,0.0%
6,Austin,TX,0,0.0%
7,Nashville,TN,0,0.0%
8,Atlanta,GA,0,0.0%
9,Miami,FL,0,0.0%
10,Dallas,TX,0,0.0%
11,San Diego,CA,0,0.0%
12,New Orleans,LA,0,0.0%
13,Washington,DC,0,0.0%
14,Denver,CO,0,0.0%
15,Boston,MA,0,0.0%
16,Phoenix,AZ,0,0.0%
17,Seattle,WA,0,0.0%
18,San Francisco,CA,0,0.0%
19,Houston,TX,0,0.0%
20,Philadelphia,PA,0,0.0%
"""

    raw_data_lines = raw_data.strip().split("\n")[1:]  # Skip header line

    for line in raw_data_lines:
        id, name, state, population, growth_rate = line.split(",")
        town = Towns(name=name, state=state, population=int(population))
        print(f"Adding town: {name}, {state} with population {population}")
        session.add(town)

    session.commit()
    session.close()
