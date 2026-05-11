import json
import os

from dotenv import load_dotenv
load_dotenv()

from tables import Events, Image, Towns, Weekends, VideoSegments
from sql_utils import get_db
import requests
from pydub import AudioSegment
from moviepy import ImageClip, VideoFileClip, concatenate_videoclips
from moviepy import VideoFileClip, CompositeVideoClip, vfx
from prefect import flow, task
from pathlib import Path

@task
def main(weekend_id=1, town_id=1):
    session = next(get_db())
    
    events = session.query(Events).filter(Events.weekend_id==weekend_id, Events.town_id==town_id).all()
    
    video_segments = session.query(VideoSegments).filter(VideoSegments.event_id.in_([e.id for e in events])).order_by(VideoSegments.timestamp).all()

    combined_video = None
    combined_audio = None
    
    for segment in video_segments:
        
        image = session.query(Image).filter(Image.id==segment.Image_id).first()
        
        print(f"Segment ID: {segment.id}, Event ID: {segment.event_id}, Timestamp: {segment.timestamp}, Script Text: {segment.script_text}, Sound File Path: {segment.sound_file_path}, Image ID: {segment.Image_id}, Image File Path: {image.file_path}")

        sound = AudioSegment.from_file(segment.sound_file_path)
        
        duration = sound.duration_seconds
        
        combined_audio = sound if combined_audio is None else combined_audio + sound
        
        image_still = ImageClip(image.file_path).with_duration(duration)
        
        if combined_video is None:
            combined_video = image_still
        else:
            combined_video = concatenate_videoclips([combined_video, image_still])
    
    combined_audio_path = "data/video/sad_talker_input/combined_audio.wav"
    
    combined_audio.export(combined_audio_path, format="wav")
    
    parent_dir = Path(__file__).parent.parent.parent.resolve()
    print(f"Parent directory: {parent_dir}")
    
    res = requests.post("http://localhost:8000/inference/", headers={"Content-Type": "application/json"}, data=json.dumps({"source_image": os.path.join(parent_dir, "data/portraits/anchor1.png"), "driven_audio": os.path.join(parent_dir, combined_audio_path), "result_dir":os.path.join(parent_dir, "data/video/sad_talker_out"), "verbose": True}))
    #res = requests.post("http://127.0.0.1:8000/inference", data='{"a":1}', headers={"Content-Type": "application/json"})
    if res.status_code != 200:
        raise Exception(f"Error: {res.status_code}, {res.text}")
        return
    
    video_path = res.json()["video_path"]
    
    
    
    # 1. Load the videos
    # 'bg_clip' is your main background
    # 'fg_clip' is the one with the green screen
    bg_clip = combined_video
    fg_clip = VideoFileClip(video_path)

    # 2. Apply the green screen mask
    # 'color' is the RGB value of the green to remove
    # 'thr' (threshold) and 's' (stiffness) help fine-tune the edges
    masked_fg = fg_clip.fx(vfx.mask_color, color=[0, 255, 0], thr=100, s=5)

    # 3. Overlay the masked clip onto the background
    # You can set the position and start time of the overlay
    final_video = CompositeVideoClip([
        bg_clip, 
        masked_fg.set_position("center").set_start(0)
    ])

    final_video.write_videofile("concatenated_output.mp4", codec="libx264", audio_codec="aac")
    
    
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    session = next(get_db())
    for e in session.query(Events).all():
        print(e.id, e.event_name)

        main(weekend_id=e.weekend_id, town_id=e.town_id)