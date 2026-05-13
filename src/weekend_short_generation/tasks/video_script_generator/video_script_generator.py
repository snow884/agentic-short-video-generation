
from dataclasses import asdict
import hashlib
import json
import os

from kokoro import KPipeline

import nest_asyncio

from research_agent import run_agent_sync


from sql_utils import get_db, populate_towns, populate_weekends
from tables import Base, Events, Image, Towns, Weekends

from pathlib import Path
from tables import VideoSegmentsList, VideoSegments

from llm import chat_ollama_with_structured_output

from sqlalchemy import inspect


import soundfile as sf
import torch
from dotenv import load_dotenv
from prefect import flow, task
import time 

load_dotenv()

def object_as_dict(obj):
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}


def populate_db_with_events(segments_list: VideoSegmentsList):

    session = next(get_db())
    
    for segment in segments_list.video_segments:
        print("Adding the segment ", segment.script_text)
        
        file_path=f"data/audio/event_{segment.event_id}_segment_{hashlib.sha256((str(segment.event_id)+str(segment.timestamp)+str(segment.script_text)).encode()).hexdigest()}.wav"
        
        generate_audio_file(segment.script_text, file_path=file_path)
        
        new_event_sql = VideoSegments(**segment.__dict__)
        new_event_sql.sound_file_path = file_path
        session.add(new_event_sql)
        
    session.commit()

    session.close()

def generate_audio_file(text, file_path='your_audio_file.wav'):
    device = 'cpu'
    pipeline = KPipeline(lang_code='a', device=device)

    generator = pipeline(text, voice='af_heart', speed=1.2)

    duration = 0

    for i, (gs, ps, audio) in enumerate(generator):
        print(i, gs, ps)
        sf.write(file_path, audio, 24000)
        info = sf.info(file_path)
        duration = duration + info.duration
        
    return duration

def check_text_spoken_length_matches_timestamps(segments_list: list):
    """
    Checks the length of each video segment's script text relative to its timestamp difference from the previous segment. If the script text length is not approximately equal to the time difference (assuming a speaking rate of 2 words per second), it returns a warning message for that segment.

    Args:
        segments_list (VideoSegmentsList): The list of video segments to check.

    Returns:
        bool: True if all segments' script text length is approximately equal to the time difference from the previous segment, otherwise False.
    """
    print(f"Checking segments length relative to timestamps for {segments_list}...")
    
    if not segments_list:
        return "You provided an empty value. No scripts segments to check."
    
    durations = [0] * len(segments_list)
    
    for i, segment in enumerate(segments_list):
        
        durations[i] = generate_audio_file(segment['script_text'])
        
        res_str = ""
        
        if (i < (len(segments_list) - 1)) and abs(( durations[i] / ((segment['timestamp'] - segments_list[i+1]['timestamp'])))-1)>0.05 :  # Assuming 2 words per second as a speaking rate
            print(f"Error: Segment number {i} at timestamp {segment['timestamp']} has script takes approximately {durations[i]} seconds to speak, but the timestamp difference to the next segment at { segments_list[i+1]['timestamp']} is {abs(segment['timestamp'] - segments_list[i+1]['timestamp'])} seconds. Adjust the timestamps or script text length for better synchronization.")
            res_str = res_str + (f"Error: Segment number {i} at timestamp {segment['timestamp']} has script takes approximately {durations[i]} seconds to speak, but the timestamp difference to the next segment number {i+1} at timestamp { segments_list[i+1]['timestamp']} is {abs(segment['timestamp'] - segments_list[i+1]['timestamp'])} seconds. Adjust the timestamps or script text length for better synchronization.")
            res_str = res_str + "\n"
        
    for i, segment in enumerate(segments_list):
        
        if (i < (len(segments_list) - 1)) and (segment['timestamp'] >= segments_list[i+1]['timestamp']):
            print(f"Error: Segment number {i} at timestamp {segment['timestamp']} has a timestamp that is not less than the next segment number {i+1} at timestamp { segments_list[i+1]['timestamp']}. Adjust the timestamps for better synchronization.")
            res_str = res_str + (f"Error: Segment number {i} at timestamp {segment['timestamp']} has a timestamp that is not less than the next segment number {i+1} at timestamp { segments_list[i+1]['timestamp']}. Adjust the timestamps for better synchronization.")
            res_str = res_str + "\n"

    for i, segment in enumerate(segments_list):
        
        if durations[i] > 6.0 or durations[i] < 4.0:
            print(f"Error: Segment number {i} at timestamp {segment['timestamp']} has a duration of {durations[i]} seconds which is outside the acceptable range of 4 to 6 seconds. Adjust the script text length for better synchronization.")
            res_str = res_str + (f"Error: Segment number {i} at timestamp {segment['timestamp']} has a duration of {durations[i]} seconds which is outside the acceptable range of 4 to 6 seconds. Adjust the script text length for better synchronization.")
            res_str = res_str + "\n"

        
    if abs(segments_list[-1]['timestamp']/180-1)>0.05:
        print(f"Error: The last segment has a timestamp of {segments_list[-1]['timestamp']} seconds which is significantly different than the expected video length of 180 seconds. Consider adjusting the timestamps or adding more segments to better utilize the video length.")
        res_str = res_str +  "The total video length is significantly different than 180 seconds."
        res_str = res_str + "\n"

    if (sum(durations) /180-1)>0.05:
        print(f"Error: The total duration of all segments is {sum(durations)} seconds which is significantly different than the expected video length of 180 seconds. Consider adjusting the timestamps or script text length for better synchronization.")
        res_str = res_str +  "The total duration of all segments is significantly different than 180 seconds."
        res_str = res_str + "\n"

    for i, segment in enumerate(segments_list):
        
        if segment['scene_description'] and len(segment['scene_description']) > 400:
            print(f"Error: Segment number {i} at timestamp {segment['timestamp']} has a scene description that is too long. Consider shortening the description for better synchronization.")
            res_str = res_str + (f"Error: Segment number {i} at timestamp {segment['timestamp']} has a scene description that is too long. Consider shortening the description for better synchronization.")
            res_str = res_str + "\n"

        if segment['scene_description'] and len(segment['scene_description']) < 100:
            print(f"Error: Segment number {i} at timestamp {segment['timestamp']} has a scene description that is too short. Consider lengthening the description for better synchronization.")
            res_str = res_str + (f"Error: Segment number {i} at timestamp {segment['timestamp']} has a scene description that is too short. Consider lengthening the description for better synchronization.")
            res_str = res_str + "\n"

    print("All segments have correct length relative to their timestamps.")

    if res_str:
        print(res_str)
        return res_str
    
    return 'success'
    
@task(task_run_name="video_script_generator_agent-{weekend_id}-{town_id}")
def main(weekend_id=0, town_id=0):
    session = next(get_db())
    
    events = session.query(Events).filter(Events.weekend_id==weekend_id, Events.town_id==town_id).all()

    if not events:
        print("No events found for the given weekend and town.")
        return

    w = session.query(Weekends).filter(Weekends.id==weekend_id).first()
    t = session.query(Towns).filter(Towns.id==town_id).first()
    
    # chat_ollama_with_structured_output(
    #     user_prompt_params={"town_name": t.name, "state": t.state, "weekend_date": w.date, "event_list":json.dumps([{"name": event.event_name,"address":event.location_address, "description": event.description, "date": event.date, "time": event.time, "id": event.id} for event in events]), "Image_list": json.dumps([{"title": m.title, "description": m.description, "id": m.id, "event_id": m.event_id} for m in images])  },
    #     system_prompt_params={}, 
    #     return_class=VideoSegmentsList, 
    #     prompt_dir=Path(__file__).parent.resolve()
    # )

    user_prompt_params={"town_name": t.name, "state": t.state, "weekend_date": w.date, "event_list":json.dumps([{"name": event.event_name,"address":event.location_address, "description": event.description, "date": event.date, "time": event.time, "id": event.id} for event in events])  }
    system_prompt_params={}

    Video_Segments_List = run_agent_sync(user_prompt_params=user_prompt_params,system_prompt_params=system_prompt_params, ReturnClass=VideoSegmentsList, prompt_dir=Path(__file__).parent.resolve(), extra_tools=[check_text_spoken_length_matches_timestamps])
    print("Received Video Segments list: ", Video_Segments_List  )
    populate_db_with_events(Video_Segments_List)


    print("clear model from vmem...")
    import ollama

    ollama.generate(model=os.getenv("RESEARCH_AGENT_MODEL"), keep_alive=0)
    time.sleep(60)  # Wait for a few seconds to ensure the model is cleared from memory

if __name__ == "__main__":
    
    main(town_id=1, weekend_id=1)