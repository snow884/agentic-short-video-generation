"""Utility helpers for creating and seeding the local SQLite database."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from video_story_generation.tables import Base

DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "local.db"
engine = create_engine(
    f"sqlite:///{DATABASE_PATH}", echo=False
)  # echo=True shows SQL logs


def get_db():
    """Yield a SQLAlchemy session bound to the local SQLite database."""

    db = Session(engine)
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all configured database tables in the local database."""

    Base.metadata.create_all(engine)


# def clear_data_for_town_weekend():

#     session = next(get_db())

#     if session.query(Weekends).first():
#         session.close()
#         return

#     session.qu
