from pathlib import Path

import soundfile as sf
from prefect import task
from run_comfy_graph import generate_audio_from_prompt

from research_agent import run_agent_sync
from sql_utils import get_db
from video_story_generation.tables import (
    PeopleAndProps,
    Videos,
    VideoSegments,
    VideoSegmentsList,
)

# from kokoro import KPipeline


VIDEO_LENGTH = 30  # seconds
SEGMENT_LENGTH = 5  # seconds


def generate_audio_file_get_duration(text, file_path="temp_audio_file.wav"):

    duration = 0

    generate_audio_from_prompt(
        text,
        output_file_path=file_path,
    )

    duration = (
        text.count(" ") / 2.0
    )  # Approximate duration based on word count (assuming 2 words per second)

    info = sf.info(file_path)
    duration = duration + info.duration

    return duration


VideoSegmentsListToolInput = VideoSegmentsList


@tool
def check_script(video_segment_list_in: VideoSegmentsListToolInput) -> str:
    """
    Validates the video segments list to ensure it meets the required criteria.

    Args:
        video_segment_list_dict (VideoSegmentsListToolInput): Video segments list to validate.

    Returns:
        str: "success" if validation passes, otherwise an error message.
    """

    res = ""

    print(
        f"Checking script with {len(video_segment_list_in.video_segments)} segments and"
        f" {len(video_segment_list_in.people_and_props)} people/props."
    )

    video_segment_list = video_segment_list_in.video_segments
    person_and_prop = video_segment_list_in.people_and_props

    # for segment_i, segment in enumerate(video_segment_list):
    #     diff1 = list(set(list(segment.keys())) ^ set([ "start_image_prompt",  "video_prompt", "people_and_props", "start_image_people_and_props_names", "narrator_script", "timestamp"]))
    #     if diff1 != []:
    #         error_text = (
    #             f"Error: Segment {segment_i} has invalid keys. Key diff = {diff1} Expected keys are: "
    #             f"{{'start_image_prompt', 'video_prompt', 'people_and_props', 'start_image_people_and_props_names', 'narrator_script', 'timestamp'}}"
    #         )
    #         print(error_text)
    #         res += error_text + "\n"

    # for person_and_prop_i, person_and_prop_item in enumerate(person_and_prop):
    #     diff1 = list(set(list(person_and_prop_item.keys())) ^ set(["name", "prompt"]))
    #     if diff1 != []:
    #         error_text = (
    #             f"Error: Person/Prop {person_and_prop_i} has invalid keys. Key diff = {diff1} Expected keys are: "
    #             f"{{'name', 'prompt'}}"
    #         )
    #         print(error_text)
    #         res += error_text + "\n"

    if res:
        return res

    for segment_i, segment in enumerate(video_segment_list):
        if not isinstance(segment.start_image_people_and_props_names, str):
            error_text = (
                f"Error: Segment {segment_i} has invalid type for"
                " 'start_image_people_and_props_names'. Expected type is str listing"
                " people and prop names separated by commas, but got"
                f" {type(segment.start_image_people_and_props_names)}."
            )
            print(error_text)
            res += error_text + "\n"

    if res:
        return res

    if (
        abs((len(video_segment_list) * SEGMENT_LENGTH - VIDEO_LENGTH) / VIDEO_LENGTH)
        > 0.20
    ):
        error_text = (
            "Error: Video segments exceed the total required video length"
            f" {VIDEO_LENGTH} s by"
            f" {(len(video_segment_list) * SEGMENT_LENGTH - VIDEO_LENGTH)/VIDEO_LENGTH * 100:.2f}%."
        )
        print(error_text)
        res += error_text + "\n"

    last_timestamp = 0
    for segment_i, segment in enumerate(video_segment_list):
        if segment_i == 0:
            if segment.timestamp != 0:
                error_text = (
                    f"Error: Segment {segment_i} has a timestamp {segment.timestamp}."
                    " The first segment's timestamp must be 0."
                )
                print(error_text)
                res += error_text + "\n"
        else:
            if (segment.timestamp - last_timestamp) != SEGMENT_LENGTH:
                error_text = (
                    f"Error: Segment {segment_i} has a timestamp"
                    f" {segment.timestamp} that is not exactly {SEGMENT_LENGTH} seconds"
                    f" after the previous segment's timestamp {last_timestamp}."
                    " Timestamps must be in ascending order and spaced by"
                    f" {SEGMENT_LENGTH} seconds."
                )
                print(error_text)
                res += error_text + "\n"

        last_timestamp = segment.timestamp

    for person_and_prop_item in person_and_prop:

        if len(person_and_prop_item.name.split(" ")) < 2:
            error_text = (
                f"Error: Person or prop '{person_and_prop_item.name}' is too short."
                " Please provide a more detailed name with at least 2 words."
            )
            print(error_text)
            res += error_text + "\n"

        if len(person_and_prop_item.name.split(" ")) > 10:
            error_text = (
                f"Error: Person or prop '{person_and_prop_item.name}' is too long."
                " Please shorten the name to less than 10 words."
            )
            print(error_text)
            res += error_text + "\n"

        if len(person_and_prop_item.prompt.split(" ")) < 40:
            error_text = (
                f"Error: Description for person or prop '{person_and_prop_item.name}'"
                " is too short. Please provide a more detailed description with at"
                " least 40 words."
            )
            print(error_text)
            res += error_text + "\n"

        if len(person_and_prop_item.prompt.split(" ")) > 120:
            error_text = (
                f"Error: Description for person or prop '{person_and_prop_item.name}'"
                " is too long. Please shorten the description to less than 120 words."
            )
            print(error_text)
            res += error_text + "\n"

        name_is_valid = all(
            char.isalnum() or char.isspace() for char in person_and_prop_item.name
        )

        if not name_is_valid:
            error_text = (
                f"Error: Person or prop '{person_and_prop_item.name}' contains invalid"
                " characters. Please use only letters, numbers, and spaces."
            )
            print(error_text)
            res += error_text + "\n"

    for segment_i, segment in enumerate(video_segment_list):

        if len(segment.start_image_prompt.split(" ")) < 40:
            error_text = (
                f"Error: The Start image prompt for segment {segment_i} is too short."
                " Please provide a more detailed prompt with more than 40 words."
            )
            print(error_text)
            res += error_text + "\n"

        if len(segment.start_image_prompt.split(" ")) > 120:
            error_text = (
                f"Error: The Start image prompt for segment {segment_i} is too long."
                " Please shorten the prompt to less than 120 words."
            )
            print(error_text)
            res += error_text + "\n"

        for prop in segment.start_image_people_and_props_names.split(","):
            if prop not in segment.start_image_prompt:
                error_text = (
                    f"Error: Prop '{prop}' in segment {segment_i} is not mentioned in"
                    " the Start image prompt. Please ensure all props/people listed"
                    " for every segment are included in the prompt."
                )
                print(error_text)
                res += error_text + "\n"

        if len(segment.video_prompt.split(" ")) < 40:
            error_text = (
                f"Error: Video prompt for segment {segment_i} is too short. Please"
                " provide a more detailed prompt with more than 40 words."
            )
            print(error_text)
            res += error_text + "\n"

        if len(segment.video_prompt.split(" ")) > 120:
            error_text = (
                f"Error: Video prompt for segment {segment_i} is too long. Please"
                " shorten the prompt to less than 120 words."
            )
            print(error_text)
            res += error_text + "\n"

        people_and_props_list = segment.start_image_people_and_props_names.split(",")

        if len(people_and_props_list) > 3:
            error_text = (
                f"Error: Segment {segment_i} has too many people and props. Please"
                " limit to 3 or fewer."
            )
            print(error_text)
            res += error_text + "\n"

        if len(people_and_props_list) == 0:
            error_text = (
                f"Error: Segment {segment_i} has no people and props. Please provide at"
                " least one."
            )
            print(error_text)
            res += error_text + "\n"

        if len(list(set(people_and_props_list))) != len(people_and_props_list):
            error_text = (
                f"Error: Segment {segment_i} has duplicate people and props. Please"
                " ensure all entries are unique."
            )
            print(error_text)
            res += error_text + "\n"

        for prop in people_and_props_list:
            if len(segment.start_image_people_and_props_names.split(",")) == 0:
                error_text = (
                    f"Error: Segment {segment_i} has an empty person or prop name."
                    " Please provide valid names."
                )
                print(error_text)
                res += error_text + "\n"

            if prop not in segment.start_image_people_and_props_names.split(","):
                error_text = (
                    f"Error: Segment {segment_i} has an invalid person or prop '{prop}'"
                    " that is not one of segment.start_image_people_and_props_names"
                    f" ('{segment.start_image_people_and_props_names.split(',')}')."
                    " Please ensure all entries are valid."
                )
                print(error_text)
                res += error_text + "\n"

    for segment_i, segment in enumerate(video_segment_list):

        duration = generate_audio_file_get_duration(
            segment.narrator_script,
            file_path=f"data/audio/temp_audio_file_{segment_i}.wav",
        )

        if abs((duration - SEGMENT_LENGTH) / SEGMENT_LENGTH) > 0.10:
            error_text = (
                f"Error: Narrator script for segment {segment_i} has a duration of"
                f" {duration:.2f} seconds, which exceeds the allowed 20% variance from"
                f" the expected {SEGMENT_LENGTH} seconds."
            )
            print(error_text)
            res += error_text + "\n"

    if res == "":
        return "success"

    return res


def add_video_segments_to_db(video_segments_list: VideoSegmentsList, session, video_id):
    """
    Adds video segments to the database.

    Args:
        video_segments_list (VideoSegmentsList): List of video segments to add.
        session: Database session.
    """

    # remove all existing segments for the video_id
    session.query(VideoSegments).filter(VideoSegments.video_id == video_id).delete()
    session.commit()

    for segment in video_segments_list.video_segments:
        new_segment = VideoSegments(
            video_prompt=segment.video_prompt,
            video_id=video_id,
            start_image_prompt=segment.start_image_prompt,
            start_image_people_and_props_names=segment.start_image_people_and_props_names,
            # stop_image_prompt=segment.stop_image_prompt,
            # stop_image_people_and_props_names=segment.stop_image_people_and_props_names,
            narrator_script=segment.narrator_script,
        )
        session.add(new_segment)
    session.commit()

    for person_and_prop in video_segments_list.people_and_props:
        new_person_and_prop = PeopleAndProps(
            video_id=video_id, name=person_and_prop.name, prompt=person_and_prop.prompt
        )
        session.add(new_person_and_prop)
    session.commit()


@task(task_run_name="generate_script")
def main(video_id):

    session = next(get_db())

    video = session.query(Videos).filter(Videos.id == video_id).first()

    user_prompt_params = {
        "video_prompt": video.prompt,
    }

    system_prompt_params = {"video_length": VIDEO_LENGTH}

    Video_Segments_List = run_agent_sync(
        user_prompt_params=user_prompt_params,
        system_prompt_params=system_prompt_params,
        # ReturnClass=VideoSegmentsList,
        ReturnClass=VideoSegmentsList,
        prompt_dir=Path(__file__).parent.resolve(),
        extra_tools=[check_script],
    )
    print("Received Video Segments List: ", Video_Segments_List)

    add_video_segments_to_db(
        video_segments_list=Video_Segments_List, session=session, video_id=video_id
    )

    # generate_audio_file_get_duration("This is a test script to check the duration of the generated audio file.", file_path="test_audio_file.wav")
    return Video_Segments_List
