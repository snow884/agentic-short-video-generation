import json
import os

from dotenv import load_dotenv
load_dotenv()

from tables import Events, Image, Towns, Weekends, VideoSegments
from sql_utils import get_db
import requests
from pydub import AudioSegment
from moviepy import ImageClip, VideoFileClip, concatenate_videoclips
from moviepy import VideoFileClip, CompositeVideoClip, vfx, TextClip
from prefect import flow, task
from pathlib import Path

import hashlib
import time
from datetime import datetime

os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

VID_HEIGHT = int(1920/2)
VID_WIDTH = int(1080/2)


@task(task_run_name="video_generator-{weekend_id}-{town_id}")
def main(weekend_id=1, town_id=1):
    session = next(get_db())
    
    events = session.query(Events).filter(Events.weekend_id==weekend_id, Events.town_id==town_id).all()
    
    w = session.query(Weekends).filter(Weekends.id==weekend_id).first()
    t = session.query(Towns).filter(Towns.id==town_id).first()
    
    video_segments = session.query(VideoSegments).filter(VideoSegments.event_id.in_([e.id for e in events])).order_by(VideoSegments.timestamp).all()

    combined_video = None
    combined_audio = None
    
    previous_event_id = video_segments[0].event_id if len(video_segments) > 0 else None
    
    for segment in video_segments:
        
        image = session.query(Image).filter(Image.id==segment.Image_id).first()
        
        print(f"Segment ID: {segment.id}, Event ID: {segment.event_id}, Timestamp: {segment.timestamp}, Script Text: {segment.script_text}, Sound File Path: {segment.sound_file_path}, Image ID: {segment.Image_id}, Image File Path: {image.file_path}")

        sound = AudioSegment.from_file(segment.sound_file_path)
        
        duration = sound.duration_seconds
        
        combined_audio = sound if combined_audio is None else combined_audio + sound
        
        image_still = ImageClip(image.file_path).with_duration(duration)
        
        clip_resized_center = image_still.resized(height=VID_HEIGHT).with_position(("center", "center"))
        
        if (not previous_event_id) or previous_event_id != segment.event_id:
            event = session.query(Events).filter(Events.id==segment.event_id).first()
            
            date_obj = datetime.strptime(event.date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%b %d")
            
            text = event.event_name 
            limit = 30
            event_name_truncated = (text[:limit] + "..") if len(text) > limit else text
            title = TextClip(
                text=event_name_truncated.title() + "\n" + formatted_date, 
                font_size=50, 
                size=(int(VID_WIDTH*0.75), None),
                color='white', 
                method='label',
                font="/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"  # Specify a font file or name
            ).with_duration(2).with_position('center')
            
            clip_resized_center = CompositeVideoClip([clip_resized_center, title])
            
            previous_event_id= segment.event_id

        if combined_video is None:
            combined_video =  CompositeVideoClip([clip_resized_center], size=(VID_WIDTH, VID_HEIGHT))
        else:
            combined_video = concatenate_videoclips([combined_video, CompositeVideoClip([clip_resized_center], size=(VID_WIDTH, VID_HEIGHT))], method="compose")
    
    combined_audio_path = "data/video/sad_talker_input/combined_audio.wav"
    
    combined_audio.export(combined_audio_path, format="wav")
    
    parent_dir = Path(__file__).parent.parent.parent.parent.parent.resolve()
    print(f"Parent directory: {parent_dir}")
    
    res = requests.post("http://localhost:8000/inference/", headers={"Content-Type": "application/json"}, data=json.dumps({"source_image": os.path.join(parent_dir, "data/portraits/anchor2.png"), "driven_audio": os.path.join(parent_dir, combined_audio_path), "result_dir":os.path.join(parent_dir, "data/video/sad_talker_out"), "checkpoint_dir":os.path.join(parent_dir, "src/services/SadTalker/checkpoints"), "enhancer":"gfpgan"}))

    if res.status_code != 200:
        raise Exception(f"Error: {res.status_code}, {res.text}")
        return
    
    video_path = res.json()["save_dir"]
    
    # 1. Load the videos
    # 'bg_clip' is your main background
    # 'fg_clip' is the one with the green screen
    bg_clip = combined_video
    fg_clip = VideoFileClip(video_path)
    final_audio = fg_clip.audio
    
    new_height = bg_clip.h / 3
    fg_clip = fg_clip.resized(height=int(new_height))

    # 2. Apply the green screen mask
    # 'color' is the RGB value of the green to remove
    # 'thr' (threshold) and 's' (stiffness) help fine-tune the edges
    masked_fg = fg_clip.with_effects([vfx.MaskColor(color=[94, 184, 99], threshold=30, stiffness=5)])
    
    masked_fg = masked_fg.with_position(("right", "bottom")).with_start(0)

    # 3. Overlay the masked clip onto the background
    # You can set the position and start time of the overlay
    
    final_video = CompositeVideoClip([
        bg_clip, 
        masked_fg
    ])
    final_video = final_video.with_audio(final_audio)
    
    # 1. Get the current Unix timestamp
    timestamp = str(time.time())

    # 2. Encode to bytes and create SHA-256 hash
    hash_object = hashlib.sha256(timestamp.encode('utf-8'))

    # 3. Get the hexadecimal representation
    hex_dig = hash_object.hexdigest()
    slug = hex_dig[0:5]  # You can take the first 10 characters for a shorter slug

    final_video.write_videofile(f"data/video/concatenated_output_{t.name}_{t.state}_{w.date}_{slug}.mp4", codec="h264_nvenc", audio_codec="aac")
    
    
    
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    session = next(get_db())
    for e in session.query(Events).all():
        print(e.id, e.event_name)

        main(weekend_id=e.weekend_id, town_id=e.town_id)