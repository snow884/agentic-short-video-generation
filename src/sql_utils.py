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
    weekends = [Weekends(date="2026-06-13")]

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
23,Chicago,IL,0,0.0%
24,Houston,TX,0,0.0%
27,San Antonio,TX,0,0.0%
31,Jacksonville,FL,0,0.0%
32,San Jose,CA,0,0.0%
33,Fort Worth,TX,0,0.0%
34,Columbus,OH,0,0.0%
35,Charlotte,NC,0,0.0%
36,Indianapolis,IN,0,0.0%
37,San Francisco,CA,0,0.0%
38,Seattle,WA,0,0.0%
39,Denver,CO,0,0.0%
40,Washington,DC,0,0.0%
41,Boston,MA,0,0.0%
42,El Paso,TX,0,0.0%
43,Nashville,TN,0,0.0%
44,Oklahoma City,OK,0,0.0%
45,Las Vegas,NV,0,0.0%
46,Detroit,MI,0,0.0%
47,Portland,OR,0,0.0%
48,Memphis,TN,0,0.0%
49,Louisville,KY,0,0.0%
50,Milwaukee,WI,0,0.0%
51,Baltimore,MD,0,0.0%
52,Albuquerque,NM,0,0.0%
53,Tucson,AZ,0,0.0%
54,Fresno,CA,0,0.0%
55,Sacramento,CA,0,0.0%
56,Kansas City,MO,0,0.0%
57,Mesa,AZ,0,0.0%
58,Atlanta,GA,0,0.0%
59,Omaha,NE,0,0.0%
60,Colorado Springs,CO,0,0.0%
61,Raleigh,NC,0,0.0%
62,Virginia Beach,VA,0,0.0%
63,Long Beach,CA,0,0.0%
64,Miami,FL,0,0.0%
65,Oakland,CA,0,0.0%
66,Minneapolis,MN,0,0.0%
67,Tulsa,OK,0,0.0%
68,Bakersfield,CA,0,0.0%
69,Wichita,KS,0,0.0%
70,Arlington,TX,0,0.0%
"""

    raw_data_lines = raw_data.strip().split("\n")[1:]  # Skip header line

    for line in raw_data_lines:
        id, name, state, population, growth_rate = line.split(",")
        town = Towns(name=name, state=state, population=int(population))
        print(f"Adding town: {name}, {state} with population {population}")
        session.add(town)

    session.commit()
    session.close()


# def clear_data_for_town_weekend():

#     session = next(get_db())

#     if session.query(Weekends).first():
#         session.close()
#         return

#     session.qu
