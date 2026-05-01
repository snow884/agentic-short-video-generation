
from dataclasses import asdict
import mimetypes


import nest_asyncio

from research_agent import run_agent_sync


from sql_utils import get_db
from tables import Image,Events, Towns, Weekends

from pathlib import Path
from tables import ImageList

import requests
import hashlib

def download_file(url, base_filename="downloaded_file"):
    # 1. Fetch the file with streaming enabled
    print(f"Downloading file from URL: {url}")
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Check for HTTP errors

        # 2. Infer extension from Content-Type header
        content_type = response.headers.get('content-type', '').split(';')[0]
        extension = mimetypes.guess_extension(content_type) or ''
        
        # 3. Construct filename and save
        filename = f"{base_filename}{extension}"
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    
        print(f"File saved as: {filename}")
    except Exception as e:
        print(f"Error downloading file: {e}")
        return False, None
    
    return True, filename
    


def populate_db_with_events(Image_list: ImageList, event_id: int):

    session = next(get_db())
    
    for new_Image in Image_list.Image:
        print("Adding the Image " + new_Image["title"] + " - " + new_Image["description"])
        url = new_Image["Image_url"]
    
        success, file_path = download_file(url, base_filename=f"data/images/event_{event_id}_Image_{hashlib.sha256(str(new_Image).encode()).hexdigest()}")
        if success:
            new_Image['file_path'] = file_path
            new_Image_sql = Image(**new_Image)
            new_Image_sql.event_id = event_id
            session.add(new_Image_sql)
            
    session.commit()
    
    session.close()


def main(event_id=0):
    session = next(get_db())
    e = session.query(Events).filter(Events.id==event_id).first()
    w = session.query(Weekends).filter(Weekends.id==e.weekend_id).first()
    t = session.query(Towns).filter(Towns.id==e.town_id).first()
    
    user_prompt_params = {
        "event_name":e.event_name,
        "town_name":t.name,
        "town_state":t.state,
        "event_date":w.date,
        "url":e.url,
        "url_facebook":e.url_facebook,
        "url_instagram":e.url_instagram
    }

    Image_list = run_agent_sync(user_prompt_params=user_prompt_params, ReturnClass=ImageList, prompt_dir=Path(__file__).parent.resolve())
    print("Received Image list: ", Image_list  )
    populate_db_with_events(Image_list, event_id=event_id)
    
    
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    session = next(get_db())
    event_id = session.query(Events.id).first()[0]
    main(event_id=event_id)