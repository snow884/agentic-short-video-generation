import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from prefect import task
from sqlalchemy import inspect

from research_agent import run_agent_sync
from sql_utils import get_db
from tables import Events, Towns, Video, VideoSchema, VideoSegments, Weekends

load_dotenv()


def object_as_dict(obj):
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}


def populate_db_vid_desc(video_id: int, video_in: VideoSchema):

    session = next(get_db())

    video = session.query(Video).filter(Video.id == video_id).first()

    video.description = video_in.description
    video.title = video_in.title

    video_file_path = video.video_file_path

    desc_file_path = video_file_path.replace(".mp4", "_desc.txt")

    if not desc_file_path:
        desc_file_path = f"data/video/description_{video_id}.txt"

    with open(desc_file_path, "w") as f:
        f.write(video_in.title + "\n" + "\n" + video_in.description)

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

    segments = (
        session.query(VideoSegments)
        .filter(VideoSegments.video_id == video.id)
        .order_by(VideoSegments.timestamp)
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

    description = f"Events in {town.name}, {town.state} on {weekend.date}: \n"

    last_event_id = None

    for segment in segments:
        if segment.event_id is None or segment.event_id in [0, -1]:
            continue

        event = session.query(Events).filter(Events.id == segment.event_id).first()

        s = segment.timestamp % 60
        m = segment.timestamp // 60
        if event:
            event_id = event.id
        else:
            event_id = None

        if event:
            if not last_event_id or event_id != last_event_id:
                description = (
                    description
                    + f"{m:02d}:{s:02d} {event.event_name} at {event.location_address}."
                    f" {event.url if event.url else ''} {event.url_facebook if event.url_facebook else ''} {event.url_instagram if event.url_instagram else ''}. \n"
                )

        last_event_id = segment.event_id

    user_prompt_params = {
        "town_name": town.name,
        "state": town.state,
        "weekend_date": weekend.date,
        "description": description,
        "events_list": json.dumps(
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
    populate_db_vid_desc(video_id=video_id, video_in=VideoData)

    print("clear model from vmem...")
    import ollama

    ollama.generate(model=os.getenv("RESEARCH_AGENT_MODEL"), keep_alive=0)
    time.sleep(60)  # Wait for a few seconds to ensure the model is cleared from memory

    print(VideoData.description)


if __name__ == "__main__":

    main(town_id=1, weekend_id=1)
