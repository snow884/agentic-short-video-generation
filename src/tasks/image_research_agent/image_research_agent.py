
from dataclasses import asdict
import mimetypes


import nest_asyncio

from research_agent import run_agent_sync


from sql_utils import get_db
from tables import Media,Events, Towns, Weekends

from pathlib import Path
from tables import MediaList

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
    


def populate_db_with_events(media_list: MediaList, event_id: int):

    session = next(get_db())
    
    for new_media in media_list.media:
        print("Adding the media " + new_media["title"] + " - " + new_media["description"])
        url = new_media["media_url"]
    
        success, file_path = download_file(url, base_filename=f"data/images/event_{event_id}_media_{hashlib.sha256(str(new_media).encode()).hexdigest()}")
        if success:
            new_media['file_path'] = file_path
            new_media_sql = Media(**new_media)
            new_media_sql.event_id = event_id
            session.add(new_media_sql)
            
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

    media_list = run_agent_sync(user_prompt_params=user_prompt_params, ReturnClass=MediaList, prompt_dir=Path(__file__).parent.resolve())
    populate_db_with_events(media_list, event_id=event_id)
    
    
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    session = next(get_db())
    event_id = session.query(Events.id).first()[0]
    main(event_id=event_id)