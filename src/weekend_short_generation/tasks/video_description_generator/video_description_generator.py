import hashlib
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from prefect import task
from sqlalchemy import inspect

from research_agent import run_agent_sync
from sql_utils import get_db
from tables import Events, Video, VideoSegments, VideoSegmentsList

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
    video_id = video.id

    for segment in segments_list.video_segments:
        print("Adding the segment ", segment.script_text)

        file_path = f"data/audio/event_{segment.event_id}_segment_{hashlib.sha256((str(segment.event_id)+str(segment.timestamp)+str(segment.script_text)).encode()).hexdigest()}.wav"

        generate_audio_file(segment.script_text, file_path=file_path)

        new_event_sql = VideoSegments(**segment.__dict__)
        new_event_sql.sound_file_path = file_path
        new_event_sql.video_id = video_id
        session.add(new_event_sql)

    session.commit()

    session.close()


@task(task_run_name="video_description_generator-{weekend_id}-{town_id}")
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

    user_prompt_params = {
        "town_name": video.town.name,
        "state": t.state,
        "weekend_date": w.date,
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

    Video_Segments_List = run_agent_sync(
        user_prompt_params=user_prompt_params,
        system_prompt_params=system_prompt_params,
        ReturnClass=VideoSegmentsList,
        prompt_dir=Path(__file__).parent.resolve(),
        extra_tools=[],
    )
    print("Received Video Segments list: ", Video_Segments_List)
    populate_db_with_events(Video_Segments_List)

    print("clear model from vmem...")
    import ollama

    ollama.generate(model=os.getenv("RESEARCH_AGENT_MODEL"), keep_alive=0)
    time.sleep(60)  # Wait for a few seconds to ensure the model is cleared from memory

    print(Video_Segments_List.video_segments[0])


if __name__ == "__main__":

    main(town_id=1, weekend_id=1)
