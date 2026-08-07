import time

import ollama
from dotenv import load_dotenv
from prefect import flow, get_run_logger
from tasks.generate_audio.generate_audio import main as generate_audio_main
from tasks.generate_people_and_prop_images.generate_people_and_prop_images import (
    main as generate_people_and_prop_images_main,
)
from tasks.generate_script.generate_script import main as generate_script_main
from tasks.generate_start_stop_images.generate_start_stop_images import (
    main as generate_start_stop_images_main,
)
from tasks.generate_video.generate_video import main as generate_video_main
from tasks.generate_video_segments.generate_video_segments import (
    main as generate_video_segments_main,
)

from sql_utils import get_db
from tables import Videos


def create_new_video_id(video_title: str = "New Video Title", prompt: str = "") -> int:
    # Implement the logic to create a new video ID

    get_run_logger().info("Creating a new video ID...")

    get_db_session = next(get_db())

    existing_video = (
        get_db_session.query(Videos).filter(Videos.name == video_title).first()
    )
    if existing_video:
        return existing_video.id

    # Create a new video record in the database
    new_video = Videos(
        prompt=prompt,
        name=video_title,  # Replace with actual title
    )
    get_db_session.add(new_video)
    get_db_session.commit()

    return new_video.id


@flow(name="Short video generator", log_prints=True)
def main_flow():
    """Run the end-to-end short generation workflow for every town in the list."""

    logger = get_run_logger()

    load_dotenv()

    video_ideas = [
        {
            "title": "Hansel and Gretel",
            "prompt": (
                "Generate a video about the story of Hansel and Gretel, brothers grim"
                " version"
            ),
        },
        {
            "title": "Little Red Riding Hood",
            "prompt": (
                "Generate a short video about the story of Little Red Riding Hood"
            ),
        },
        {
            "title": "3 little pigs as wolf",
            "prompt": (
                "Generate a short video about the story of the Three Little Pigs from"
                " the wolf's perspective"
            ),
        },
        {
            "title": "The Ant and the Grasshopper",
            "prompt": (
                "Generate a short video about the story of the Ant and the Grasshopper"
            ),
        },
    ]

    for video_idea in video_ideas:
        video_id = create_new_video_id(
            video_title=video_idea["title"],
            prompt=video_idea["prompt"],
        )

        generate_script_main(video_id=video_id)

        logger.info("Waiting 10s to clear model from memory...")

        ollama.generate(model="qwen3.6:27b-q4_K_M", keep_alive=0)
        time.sleep(
            10
        )  # Wait for a few seconds to ensure the model is cleared from memory

        generate_people_and_prop_images_main(video_id=video_id)

        generate_start_stop_images_main(video_id=video_id)

        generate_video_segments_main(video_id=video_id)

        generate_audio_main(video_id=video_id)

        generate_video_main(video_id=video_id)


if __name__ == "__main__":
    main_flow()
