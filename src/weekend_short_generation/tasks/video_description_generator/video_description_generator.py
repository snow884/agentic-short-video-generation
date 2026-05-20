import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from prefect import task
from sqlalchemy import inspect

from research_agent import run_agent_sync
from sql_utils import get_db
from tables import Events, Towns, Video, VideoSchema, VideoSegmentsList

load_dotenv()


def object_as_dict(obj):
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}


def populate_db_vid_desc(segments_list: VideoSegmentsList):

    session = next(get_db())

    event_id = [vs.event_id for vs in segments_list.video_segments if vs.event_id][0]

    event = session.query(Events).filter(Events.id == event_id).first()

    video = Video(
        town_id=event.town_id,
        weekend_id=event.weekend_id,
        video_file_path="",
        audio_file_path="",
    )
    session.add(video)
    session.commit()

    session.commit()

    session.close()


@task(task_run_name="video_description_generator-{video_id}")
def main(video_id):
    session = next(get_db())

    video = session.query(Video).filter(Video.id == video_id).first()

    events = (
        session.query(Events)
        .filter(Events.weekend_id == video.weekend_id, Events.town_id == video.town_id)
        .all()
    )

    if not events:
        print("No events found for the given weekend and town.")
        return

    # chat_ollama_with_structured_output(
    #     user_prompt_params={"town_name": t.name, "state": t.state, "weekend_date": w.date, "event_list":json.dumps([{"name": event.event_name,"address":event.location_address, "description": event.description, "date": event.date, "time": event.time, "id": event.id} for event in events]), "Image_list": json.dumps([{"title": m.title, "description": m.description, "id": m.id, "event_id": m.event_id} for m in images])  },
    #     system_prompt_params={},
    #     return_class=VideoSegmentsList,
    #     prompt_dir=Path(__file__).parent.resolve()
    # )

    town_id = (
        session.query(Events)
        .filter(Events.weekend_id == video.weekend_id, Events.town_id == video.town_id)
        .first()
        .town_id
    )

    town = session.query(Towns).filter(Towns.id == town_id).first()

    weekend_id = (
        session.query(Events)
        .filter(Events.weekend_id == video.weekend_id, Events.town_id == video.town_id)
        .first()
        .weekend_id
    )

    weekend = session.query(Weekends).filter(Weekends.id == weekend_id).first()

    user_prompt_params = {
        "town_name": town.name,
        "state": town.state,
        "weekend_date": weekend.date,
        "event_list": json.dumps(
            [
                {
                    "name": event.event_name,
                    "address": event.location_address,
                    "description": event.description,
                    "date": event.date,
                    "time": event.time,
                    "id": event.id,
                }
                for event in events
            ]
        ),
        "segment_list": json.dumps(
            [
                {
                    "name": event.event_name,
                    "address": event.location_address,
                    "description": event.description,
                    "date": event.date,
                    "time": event.time,
                    "id": event.id,
                }
                for event in events
            ]
        ),
    }
    system_prompt_params = {}

    VideoData = run_agent_sync(
        user_prompt_params=user_prompt_params,
        system_prompt_params=system_prompt_params,
        ReturnClass=VideoSchema,
        prompt_dir=Path(__file__).parent.resolve(),
        extra_tools=[],
    )
    print("Received Video data: ", VideoData)
    populate_db_vid_desc(VideoData)

    print("clear model from vmem...")
    import ollama

    ollama.generate(model=os.getenv("RESEARCH_AGENT_MODEL"), keep_alive=0)
    time.sleep(60)  # Wait for a few seconds to ensure the model is cleared from memory

    print(VideoData.description)


if __name__ == "__main__":

    main(town_id=1, weekend_id=1)
