import os
import time

import ollama
from dotenv import load_dotenv
from prefect import flow, get_run_logger
from tasks.generate_audio.generate_audio import main as generate_audio_main
from tasks.generate_people_and_prop_images.generate_people_and_prop_images import (
    main as generate_people_and_prop_images_main,
)
from tasks.generate_start_stop_images.generate_start_stop_images import (
    main as generate_start_stop_images_main,
)
from tasks.generate_video.generate_video import main as generate_video_main
from tasks.generate_video_feedback.generate_video_feedback import (
    main as generate_video_feedback_main,
)
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
                "Generate a video about adult Hansel and Gretel, with bad ending"
                " where the witch wins and fattens Gretel."
            ),
        },
        {
            "title": "Little Red Riding Hood",
            "prompt": (
                "Generate a short video about the story of Little Red Riding Hood, with"
                " bad ending where the wolf wins and eats the grandmother and Little"
                " Red Riding Hood."
            ),
        },
        {
            "title": "The Gingerbread Man",
            "prompt": (
                "Generate a short video about the story of The Gingerbread Man, with"
                " bad ending where the fox wins and eats the gingerbread man."
            ),
        },
    ]

    for video_idea in video_ideas:

        video_id = create_new_video_id(
            video_title=video_idea["title"],
            prompt=video_idea["prompt"],
        )

        for i in range(0, 3):

            # video_id = 1  # Replace with the actual video ID you want to use

            # generate_script_main(video_id=video_id)

            logger.info("Waiting 10s to clear model from memory...")

            ollama.generate(
                model=os.getenv("RESEARCH_AGENT_MODEL", "qwen3.6:27b-q4_K_M"),
                keep_alive=0,
            )
            time.sleep(
                10
            )  # Wait for a few seconds to ensure the model is cleared from memory

            generate_people_and_prop_images_main(video_id=video_id)

            generate_start_stop_images_main(video_id=video_id)

            generate_video_segments_main(video_id=video_id)

            generate_audio_main(video_id=video_id)

            generate_video_main(video_id=video_id)

            generate_video_feedback_main(video_id=video_id)


if __name__ == "__main__":
    main_flow()
