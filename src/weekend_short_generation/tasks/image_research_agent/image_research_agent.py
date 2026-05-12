
from dataclasses import asdict
import mimetypes

import ollama



import nest_asyncio

from research_agent import run_agent_sync


from sql_utils import get_db
from tables import Image,Events, Towns, Weekends

from pathlib import Path
from tables import ImageList

import requests
import hashlib
from prefect import flow, task
from prefect.logging import get_run_logger

def describe_image(img_bytes):
    
    response = ollama.chat(
        model='qwen3.6:27b',
        messages=[{
            'role': 'user',
            'content': 'What is in this image? One paragraph description.',
            'images': [img_bytes] 
        }]
    )

    return (response['message']['content'])


def check_image_url(url):
    """
    check image url and provide description

    Args:
        url (str): url to check

    Returns:
        str: description of the image or error message
    """
    try:
        response = requests.get(url, allow_redirects=True, timeout=5)
        if response.status_code == 200:
            image_bytes = response.content
            description = describe_image(image_bytes)
            print("success: image loaded successfully, image description: " + description)
            return "success: image loaded successfully, image description: " + description
        else:
            print(f"error: URL did not point to a valid image or was not accessible, received code {response.status_code}")
            return f"error: URL did not point to a valid image or was not accessible, received code {response.status_code}"
        
    except Exception as e:
        print(f"error: cant load the file, exception: {e}")
        return "error: cant load the file"
    

def download_file(url, base_filename="downloaded_file"):
    logger = get_run_logger()
    # 1. Fetch the file with streaming enabled
    logger.info(f"Downloading file from URL: {url}")
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
    
    for new_Image in Image_list.images:
        print("Adding the Image " + new_Image.title + " - " + new_Image.description)
        url = new_Image.image_url
    
        success, file_path = download_file(url, base_filename=f"data/images/event_{event_id}_Image_{hashlib.sha256(str(new_Image).encode()).hexdigest()}")
        if success:
            new_Image_sql = Image(**new_Image.__dict__)
            new_Image_sql.file_path = file_path
            new_Image_sql.event_id = event_id
            session.add(new_Image_sql)
            
    session.commit()
    
    session.close()

@task(task_run_name="image_research_agent-{event_id}")
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

    Image_list = run_agent_sync(user_prompt_params=user_prompt_params, system_prompt_params={"num_images": 5}, ReturnClass=ImageList, prompt_dir=Path(__file__).parent.resolve(), extra_tools=[check_image_url])
    print("Received Image list: ", Image_list  )
    populate_db_with_events(Image_list, event_id=event_id)
    
    
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    session = next(get_db())
    for e in session.query(Events).all():
        print(e.id, e.event_name)
        event_id = e.id
        main(event_id=event_id)