"""Initialize the local database tables for the weekend short generation workflow."""

import os
import shutil

from dotenv import load_dotenv
from prefect import flow, task


@task
def create_tables():
    """Recreate the local database schema and seed the initial reference data."""

    from sqlalchemy import create_engine

    from tables import Base

    os.remove("data/local.db") if os.path.exists("data/local.db") else None

    engine = create_engine(
        "sqlite:///data/local.db", echo=False
    )  # echo=True shows SQL logs

    Base.metadata.create_all(engine)


@flow(name="Short video generator - Initialization")
def main_flow():
    """Entry point for initializing the workflow database state."""

    load_dotenv()

    # clear all files in /data/images/ and /data/audio/
    for folder in ["data/images", "data/audio", "data/video"]:
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}. Reason: {e}")

    create_tables()


if __name__ == "__main__":
    main_flow()
