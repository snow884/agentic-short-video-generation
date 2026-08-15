import json
import os
from pathlib import Path

import ollama
import soundfile as sf
from prefect import task

from research_agent import run_agent_sync
from sql_utils import get_db
from video_story_generation.run_comfy_graph import generate_audio_from_prompt
from video_story_generation.tables import (
    PeopleAndProps,
    Videos,
    VideoSegments,
    VideoSegmentsList,
)

# from kokoro import KPipeline


VIDEO_LENGTH = 40  # seconds
ALLOWED_TIME_VARIANCE = 0.333  # 30% variance allowed in segment timing

SEGMENT_LENGTH = 5  # seconds
TARGET_SEGMENT_COUNT = VIDEO_LENGTH // SEGMENT_LENGTH

# Full validation can be expensive for longer scripts; default to fast mode when
# generating videos longer than 30 seconds.
FAST_VALIDATION_DEFAULT = VIDEO_LENGTH > 60
ENABLE_FAST_VALIDATION = (
    os.getenv(
        "CHECK_SCRIPT_FAST_VALIDATION",
        "1" if FAST_VALIDATION_DEFAULT else "0",
    )
    == "1"
)
ENABLE_AUDIO_DURATION_CHECK = os.getenv("CHECK_SCRIPT_AUDIO_DURATION", "1") == "1"
ENABLE_LLM_CONSISTENCY_CHECKS = os.getenv("CHECK_SCRIPT_LLM_CONSISTENCY", "1") == "1"


def generate_audio_file_get_duration(text, file_path="temp_audio_file.wav"):

    # duration = 0

    generate_audio_from_prompt(
        text,
        output_file_path=file_path,
    )

    # duration = (
    #     text.count(" ") / 2.0
    # )  # Approximate duration based on word count (assuming 2 words per second)

    # duration = (
    #     text.count(" ") / 2.0
    # )  # Approximate duration based on word count (assuming 2 words per second)

    info = sf.info(file_path)
    duration = info.duration

    return duration


def estimate_narrator_duration_seconds(text: str) -> float:
    """Estimate narration duration quickly using a typical narration pace."""
    words = len(text.split())
    words_per_second = 2.5
    return words / words_per_second


def check_script(video_script: dict) -> str:
    """
    Validates the video script to ensure it meets the required criteria.

    Args:
        video_script (dict): Video script structure.

        Structure of video_script:
        {
            "video_segments": [
                {
                    "start_image_prompt": str,
                    "video_prompt": str,
                    "people_and_props": list,
                    "start_image_people_and_props_names": str,
                    "narrator_script": str,
                    "timestamp": int
                },
                ...
            ],
            "people_and_props": [
                {
                    "name": str,
                    "prompt": str
                },
                ...
            ]
        }

    Returns:
        str: "success" if validation passes, otherwise an error message.
    """

    res = ""

    video_segment_list_in = video_script

    print(
        f"Checking script with {len(video_segment_list_in['video_segments'])} segments"
        f" and {len(video_segment_list_in['people_and_props'])} people/props."
    )

    video_segment_list = video_segment_list_in["video_segments"]
    person_and_prop = video_segment_list_in["people_and_props"]

    for segment_i, segment in enumerate(video_segment_list):
        diff1 = list(
            set(list(segment.keys()))
            ^ set(
                [
                    "start_image_prompt",
                    "video_prompt",
                    "start_image_people_and_props_names",
                    "narrator_script",
                    "timestamp",
                ]
            )
        )

        if diff1 != []:
            error_text = (
                f"Error: Segment {segment_i} has invalid keys. Key diff ="
                f" {diff1} Expected keys are: {{'start_image_prompt', 'video_prompt',"
                " 'start_image_people_and_props_names',"
                " 'narrator_script', 'timestamp'}"
            )
            print(error_text)
            res += error_text + "\n"

    for person_and_prop_i, person_and_prop_item in enumerate(person_and_prop):
        try:
            diff1 = list(
                set(list(person_and_prop_item.keys())) ^ set(["name", "prompt"])
            )
            if diff1 != []:
                error_text = (
                    f"Error: Person/Prop {person_and_prop_i} has invalid keys. Key diff"
                    f" = {diff1} Expected keys are: {{'name', 'prompt'}}"
                )
                print(error_text)
                res += error_text + "\n"
        except Exception as e:
            error_text = (
                f"Error: Person/Prop {person_and_prop_i} has invalid structure."
                f" Exception: {e}"
            )
            print(error_text)
            res += error_text + "\n"

    if res:
        return res

    for segment_i, segment in enumerate(video_segment_list):
        if not isinstance(segment["start_image_people_and_props_names"], str):
            error_text = (
                f"Error: Segment {segment_i} has invalid type for"
                " 'start_image_people_and_props_names'. Expected type is str listing"
                " people and prop names separated by commas, but got"
                f" {type(segment['start_image_people_and_props_names'])}."
            )
            print(error_text)
            res += error_text + "\n"

    if res:
        return res

    if (
        abs((len(video_segment_list) * SEGMENT_LENGTH - VIDEO_LENGTH) / VIDEO_LENGTH)
        > ALLOWED_TIME_VARIANCE
    ):
        error_text = (
            "Error: Video segments exceed the total required video length"
            f" {VIDEO_LENGTH} s by"
            f" {(len(video_segment_list) * SEGMENT_LENGTH - VIDEO_LENGTH)/VIDEO_LENGTH * 100:.2f}%"
            f" (allowed variance: {ALLOWED_TIME_VARIANCE * 100:.2f}%)."
        )
        print(error_text)
        res += error_text + "\n"

    last_timestamp = 0
    for segment_i, segment in enumerate(video_segment_list):
        if segment_i == 0:
            if segment["timestamp"] != 0:
                error_text = (
                    f"Error: Segment {segment_i} has a timestamp"
                    f" {segment['timestamp']}. The first segment's timestamp must be 0."
                )
                print(error_text)
                res += error_text + "\n"
        else:
            if (segment["timestamp"] - last_timestamp) != SEGMENT_LENGTH:
                error_text = (
                    f"Error: Segment {segment_i} has a timestamp"
                    f" {segment['timestamp']} that is not exactly"
                    f" {SEGMENT_LENGTH} seconds after the previous segment's timestamp"
                    f" {last_timestamp}. Timestamps must be in ascending order and"
                    f" spaced by {SEGMENT_LENGTH} seconds."
                )
                print(error_text)
                res += error_text + "\n"

        last_timestamp = segment["timestamp"]

    for person_and_prop_item in person_and_prop:

        if len(person_and_prop_item["name"]) < 1:
            error_text = (
                f"Error: Person or prop '{person_and_prop_item['name']}' is too short."
                " Please provide a more detailed name with at least 1 letter."
            )
            print(error_text)
            res += error_text + "\n"

        if len(person_and_prop_item["name"].split(" ")) > 10:
            error_text = (
                f"Error: Person or prop '{person_and_prop_item['name']}' is too long."
                " Please shorten the name to less than 10 words."
            )
            print(error_text)
            res += error_text + "\n"

        if len(person_and_prop_item["prompt"].split(" ")) < 40:
            error_text = (
                "Error: Description for person or prop"
                f" '{person_and_prop_item['name']}' is too short. Please provide a more"
                " detailed description with at least 40 words."
            )
            print(error_text)
            res += error_text + "\n"

        if len(person_and_prop_item["prompt"].split(" ")) > 120:
            error_text = (
                "Error: Description for person or prop"
                f" '{person_and_prop_item['name']}' is too long. Please shorten the"
                " description to less than 120 words."
            )
            print(error_text)
            res += error_text + "\n"

        name_is_valid = all(
            char.isalnum() or char.isspace() for char in person_and_prop_item["name"]
        )

        if not name_is_valid:
            error_text = (
                f"Error: Person or prop '{person_and_prop_item['name']}' contains"
                " invalid characters. Please use only letters, numbers, and spaces."
            )
            print(error_text)
            res += error_text + "\n"

    for segment_i, segment in enumerate(video_segment_list):

        if len(segment["start_image_prompt"].split(" ")) < 40:
            error_text = (
                f"Error: The Start image prompt for segment {segment_i} is too short."
                " Please provide a more detailed prompt with more than 40 words."
            )
            print(error_text)
            res += error_text + "\n"

        if len(segment["start_image_prompt"].split(" ")) > 8400:
            error_text = (
                f"Error: The Start image prompt for segment {segment_i} is too long."
                " Please shorten the prompt to less than 80 words."
            )
            print(error_text)
            res += error_text + "\n"

        for prop in segment["start_image_people_and_props_names"].split(","):
            if prop not in segment["start_image_prompt"]:
                error_text = (
                    f"Error: Prop '{prop}' in segment {segment_i} is not mentioned in"
                    " the Start image prompt. Please ensure all props/people listed"
                    " for every segment are included in the prompt."
                )
                print(error_text)
                res += error_text + "\n"

        if len(segment["video_prompt"].split(" ")) < 20:
            error_text = (
                f"Error: Video prompt for segment {segment_i} is too short. Please"
                " provide a more detailed prompt with more than 20 words."
            )
            print(error_text)
            res += error_text + "\n"

        if len(segment["video_prompt"].split(" ")) > 80:
            error_text = (
                f"Error: Video prompt for segment {segment_i} is too long. Please"
                " shorten the prompt to less than 80 words."
            )
            print(error_text)
            res += error_text + "\n"

        people_and_props_list = segment["start_image_people_and_props_names"].split(",")

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
            if len(segment["start_image_people_and_props_names"].split(",")) == 0:
                error_text = (
                    f"Error: Segment {segment_i} has an empty person or prop name."
                    " Please provide valid names."
                )
                print(error_text)
                res += error_text + "\n"

            if prop not in segment["start_image_people_and_props_names"].split(","):
                error_text = (
                    f"Error: Segment {segment_i} has an invalid person or prop '{prop}'"
                    " that is not one of segment.start_image_people_and_props_names"
                    f" ('{segment['start_image_people_and_props_names'].split(',')}')."
                    " Please ensure all entries are valid."
                )
                print(error_text)
                res += error_text + "\n"

            for p in person_and_prop:
                if segment["start_image_prompt"].find(p["name"].lower()) != -1:
                    if p["name"].lower() not in [
                        name.lower()
                        for name in segment["start_image_people_and_props_names"].split(
                            ","
                        )
                    ]:
                        error_text = (
                            f"Error: Segment {segment_i} has a person or prop"
                            f" '{p['name']}' that is mentioned in the start image"
                            " prompt but not listed in"
                            " start_image_people_and_props_names. Please ensure all"
                            " people and props mentioned in the prompt are included in"
                            " the list."
                        )
                        print(error_text)
                        res += error_text + "\n"

                if segment["video_prompt"].find(p["name"].lower()) != -1:
                    if p["name"].lower() not in [
                        name.lower()
                        for name in segment["start_image_people_and_props_names"].split(
                            ","
                        )
                    ]:
                        error_text = (
                            f"Error: Segment {segment_i} has a person or prop"
                            f" '{p['name']}' that is mentioned in the video prompt but"
                            " not listed in start_image_people_and_props_names. Please"
                            " ensure all people and props mentioned in the prompt are"
                            " included in the list."
                        )
                        print(error_text)
                        res += error_text + "\n"

    for segment_i, segment in enumerate(video_segment_list):

        if ENABLE_AUDIO_DURATION_CHECK:
            duration = generate_audio_file_get_duration(
                segment["narrator_script"],
                file_path=f"data/audio/temp_audio_file_{segment_i}.wav",
            )
        else:
            duration = estimate_narrator_duration_seconds(segment["narrator_script"])

        if abs((duration - SEGMENT_LENGTH) / SEGMENT_LENGTH) > ALLOWED_TIME_VARIANCE:
            error_text = (
                f"Error: Narrator script for segment {segment_i} has a duration of"
                f" {duration:.2f} seconds, which exceeds the allowed"
                f" {ALLOWED_TIME_VARIANCE * 100:.2f}% variance from the expected"
                f" {SEGMENT_LENGTH} seconds."
            )
            print(error_text)
            res += error_text + "\n"

    # Skip expensive LLM consistency checks by default for long videos.
    if not ENABLE_FAST_VALIDATION or ENABLE_LLM_CONSISTENCY_CHECKS:
        check_start_image_prompt_props_res = check_start_image_prompt_props(
            video_segment_list=video_segment_list, people_and_props=person_and_prop
        )

        if "success" not in check_start_image_prompt_props_res:
            res += check_start_image_prompt_props_res + "\n"

        for segment_i, segment in enumerate(video_segment_list):
            check_start_image_prompt_props_res = (
                check_start_image_to_prompt_consistency(
                    start_image_prompt=segment["start_image_prompt"],
                    video_prompt=segment["video_prompt"],
                )
            )

            if "success" not in check_start_image_prompt_props_res:
                res += (
                    f"Segment {segment_i}: " + check_start_image_prompt_props_res + "\n"
                )

    if not ENABLE_FAST_VALIDATION and ENABLE_LLM_CONSISTENCY_CHECKS:
        for segment_i, segment in enumerate(video_segment_list):
            check_start_image_video_prompt_consistency_res = (
                check_start_image_video_prompt_consistency(segment=segment)
            )

            if "success" not in check_start_image_video_prompt_consistency_res:
                res += (
                    f"Segment {segment_i}: "
                    + check_start_image_video_prompt_consistency_res
                    + "\n"
                )

    # if not ENABLE_FAST_VALIDATION and ENABLE_LLM_CONSISTENCY_CHECKS:
    #     for segment_i, segment in enumerate(video_segment_list):
    #         check_video_prompt_simplicity_res = check_video_prompt_simplicity(segment)

    #         if "success" not in check_video_prompt_simplicity_res:
    #             res += (
    #                 f"Segment {segment_i}: " + check_video_prompt_simplicity_res + "\n"
    #             )

    if res == "":
        print("Script validation passed successfully. No errors found.")
        return "success"

    return res


def check_start_image_to_prompt_consistency(
    start_image_prompt: str, video_prompt: str
) -> str:

    """
    Validates that the start image prompt and video prompt are consistent with each other.

    Args:
        start_image_prompt (str): The prompt for the start image.
        video_prompt (str): The prompt for the video.

    Returns:
        str: "success" if validation passes, otherwise an error message.
    """

    llm_prompt = f"""
    Compare these two prompts.

    Rule: every character, object, or prop named in Video Prompt must already appear in Start Image Prompt. Match strictly; shortened, grouped, or renamed references count as mismatches.

    Return JSON only:
    {{
      "non_matching_objects_or_persons": [
        {{"name": "<string>", "reason": "<string>"}}
      ]
    }}

    Return an empty list when there are no mismatches.

    Start Image Prompt: {start_image_prompt}
    Video Prompt: {video_prompt}
    """

    res = ollama.chat(
        model=os.getenv("RESEARCH_AGENT_MODEL", "qwen3.6:27b-q4_K_M"),
        messages=[{"role": "user", "content": llm_prompt}],
        think=False,
        format="json",
        options={
            "temperature": 0,
            "num_predict": 2000,
        },
    )
    print(res)
    try:
        content_json = json.loads(res["message"]["content"])
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        print(f"Response content: {res['message']['content']}")
        return "Error: Failed to decode JSON from LLM response."

    if "non_matching_objects_or_persons" not in content_json.keys():
        return "success"

    if not content_json["non_matching_objects_or_persons"]:
        return "success"

    else:
        non_matching_list = content_json["non_matching_objects_or_persons"]
        error_messages = []
        for item in non_matching_list:
            error_messages.append(
                f"'{item['name']}' is mentioned in video prompt but missing for start"
                f" image prompt, reason: {item['reason']}."
            )
        return "\n".join(error_messages)


def check_start_image_prompt_props(
    video_segment_list: list[dict], people_and_props: list[dict]
) -> str:
    """
    Look for all items in the start_image_prompt for references to objects or people that appear more than once and should be
    props. Then compare those objects to the list of people_and_props to ensure that they are included. If any are missing, return an error message.

    Include more general matches

    Args:
        video_segment_list (list[dict]): A list of video segments, each containing a start image prompt and a video prompt.
        people_and_props (list[dict]): A list of people and props associated with the video segments.

    Returns:
        str: "success" if validation passes, otherwise an error message.
    """
    start_image_prompts = "\n ".join(
        [
            "Segment " + str(i) + ": " + s["start_image_prompt"]
            for i, s in enumerate(video_segment_list)
        ]
    )

    llm_prompt = f"""
    Find objects or people that appear in 2 or more start-image prompts but are missing from props_list.

    Report only repeated objects and people that should be added to people_and_props.

    Return JSON only:
    {{
      "missing_props": [
        {{"prop_name": "<string>", "segment_index": <int>, "reason": "<string>"}}
      ]
    }}

    Return an empty list when nothing is missing.

    segments:
    {start_image_prompts}

    props_list:
    {', '.join([p['name'] for p in people_and_props])}
    """
    print(
        f"Running repeated-prop validation across {len(video_segment_list)} segments."
    )

    res = ollama.chat(
        model=os.environ["RESEARCH_AGENT_MODEL"],
        messages=[{"role": "user", "content": llm_prompt}],
        format="json",
        think=False,
        options={
            "temperature": 0,
            "num_predict": 2000,
        },
    )
    print(res)
    try:
        content_json = json.loads(res["message"]["content"])
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        print(f"Response content: {res['message']['content']}")
        return "Error: Failed to decode JSON from LLM response."

    if "missing_props" not in content_json.keys():
        return "success"

    if not content_json["missing_props"]:
        return "success"

    else:
        missing_props_list = content_json["missing_props"]
        error_messages = []
        for missing_prop in missing_props_list:
            error_messages.append(
                f"Error: Prop '{missing_prop['prop_name']}' is missing from the list of"
                f" people_and_props for segment {missing_prop['segment_index']},"
                f" reason: {missing_prop['reason']}."
            )
        return "\n".join(error_messages)


def check_start_image_video_prompt_consistency(segment: dict) -> str:
    """
    Look at the start image prompt and video prompt for a segment and ensure that the start image prompt describes objects before action/activity and the video prompt describes same objects/people performing action/activity.

    For example:

    If the image prompt describes "a young boy sitting at a table" and the video prompt describes "the young boy stands up and walks to the door", then this is consistent.
    If the image prompt describes "a young boy sitting at a table" and the video prompt describes "the young boy is still sitting at the table", then this is also consistent.
    If the image prompt describes "a young boy sitting at a table" and the video prompt describes "a young girl walks into the room", then this is inconsistent because the young girl is not mentioned in the start image prompt.
    If the image prompt describes "a young boy sitting at a table" and the video prompt describes "the young boy runs a marathon", then this is inconsistent because the young boy is not performing an action that is consistent with the start image prompt.
    If the image prompt describes "a young boy and a girl sitting at a table" and the video prompt describes "children stand up and walk to the door", then this is inconsistent because the two prompts refer in a different way to the same characters.

    Args:
        segment (dict): A video segment containing a start image prompt and a video prompt.

    Returns:
        str: "success" if validation passes, otherwise an error message.
    """

    llm_prompt = f"""
    Look at the start image prompt and video prompt for a segment and ensure that the start image prompt describes objects before action/activity and the video prompt describes same objects/people performing action/activity.

    For example:

    If the image prompt describes "a young boy sitting at a table" and the video prompt describes "the young boy stands up and walks to the door", then this is consistent.
    If the image prompt describes "a young boy sitting at a table" and the video prompt describes "the young boy is still sitting at the table", then this is also consistent.
    If the image prompt describes "a young boy sitting at a table" and the video prompt describes "a young girl walks into the room", then this is inconsistent because the young girl is not mentioned in the start image prompt.
    If the image prompt describes "a young boy sitting at a table" and the video prompt describes "the young boy runs a marathon", then this is inconsistent because the young boy is not performing an action that is consistent with the start image prompt.
    If the image prompt describes "a young boy and a girl sitting at a table" and the video prompt describes "children stand up and walk to the door", then this is inconsistent because the two prompts refer in a different way to the same characters.

    Return JSON only:
    {{
      "inconsistencies": [
        {{"reason_and_fix": "<string>"}}
      ]
    }}

    Return an empty list when they are consistent.

    start_image_prompt:
    {segment['start_image_prompt']}
    video_prompt:
    {segment['video_prompt']}
    """
    print("Running start-image/video consistency validation.")

    res = ollama.chat(
        model=os.environ["RESEARCH_AGENT_MODEL"],
        messages=[{"role": "user", "content": llm_prompt}],
        format="json",
        think=False,
        options={
            "temperature": 0,
            "num_predict": 2000,
        },
    )
    print(res)
    try:
        content_json = json.loads(res["message"]["content"])
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        print(f"Response content: {res['message']['content']}")
        return "Error: Failed to decode JSON from LLM response."

    if "inconsistencies" not in content_json.keys():
        return "success"

    if not content_json["inconsistencies"]:
        return "success"

    else:
        inconsistencies_list = content_json["inconsistencies"]
        error_messages = []
        for inconsistency in inconsistencies_list:
            error_messages.append(f"Error: {inconsistency['reason_and_fix']}")
        return "\n".join(error_messages)


# def check_video_prompt_simplicity(segment: dict) -> str:
#     """
#     Checks whether the video prompt only includes one action by one person or one group of people. It must not include multiple actions following each other, or complex or abstract concepts.

#     Args:
#         segment (dict): A video segment containing the video prompt.

#     Returns:
#         str: "success" if the video prompt is simple, otherwise an error message.
#     """

#     llm_prompt = f"""
#     Check that the video prompt only includes one simple action other than the camera movement, and does not include complex or abstract concepts.

#     Return JSON only:
#     {{
#       "explanation": [
#         {{"reason_and_fix": "<string>"}}
#       ]
#     }}

#     Return an empty explanation list when the video prompt is simple.

#     video_prompt:
#     {segment['video_prompt']}
#     """
#     print("Running video prompt simplicity validation.")

#     res = ollama.chat(
#         model=os.environ["RESEARCH_AGENT_MODEL"],
#         messages=[{"role": "user", "content": llm_prompt}],
#         format="json",
#         think=False,
#         options={
#             "temperature": 0,
#             "num_predict": 2000,
#         },
#     )
#     print(res)
#     try:
#         content_json = json.loads(res["message"]["content"])
#     except json.JSONDecodeError as e:
#         print(f"Error decoding JSON: {e}")
#         print(f"Response content: {res['message']['content']}")
#         return "Error: Failed to decode JSON from LLM response."

#     if "explanation" not in content_json.keys():
#         return "success"

#     if not content_json["explanation"]:
#         return "success"

#     else:
#         explanation_list = content_json["explanation"]
#         error_messages = []
#         for explanation in explanation_list:
#             error_messages.append(f"Error: {explanation['reason_and_fix']}")
#         return "\n".join(error_messages)


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
        "video_length": VIDEO_LENGTH,
        "segment_length": SEGMENT_LENGTH,
        "target_segment_count": TARGET_SEGMENT_COUNT,
    }

    system_prompt_params = {
        "video_length": VIDEO_LENGTH,
        "segment_length": SEGMENT_LENGTH,
        "target_segment_count": TARGET_SEGMENT_COUNT,
        "max_validation_passes": 2,
    }

    Video_Segments_List = run_agent_sync(
        user_prompt_params=user_prompt_params,
        system_prompt_params=system_prompt_params,
        # ReturnClass=VideoSegmentsList,
        ReturnClass=VideoSegmentsList,
        prompt_dir=Path(__file__).parent.resolve(),
        extra_tools=[check_script],
    )
    print("Received Video Segments List: ", Video_Segments_List)

    # create folder if it doesn't exist
    os.makedirs("data/data", exist_ok=True)

    json_output_path = f"data/data/script_{video_id}.json"
    with open(json_output_path, "w") as f:
        json.dump(Video_Segments_List.dict(), f, indent=4)

    add_video_segments_to_db(
        video_segments_list=Video_Segments_List, session=session, video_id=video_id
    )

    # generate_audio_file_get_duration("This is a test script to check the duration of the generated audio file.", file_path="test_audio_file.wav")
    return Video_Segments_List


if __name__ == "__main__":

    print(
        check_script(
            {
                "video_segments": [
                    {
                        "video_prompt": (
                            "The camera slowly pushes in toward Young Hansel and Young"
                            " Gretel's anxious faces throughout the shot. Young Hansel"
                            " looks around nervously scanning the dark forest while"
                            " Young Gretel keeps her arms wrapped tightly around"
                            " herself. Leaves rustle gently in the cold wind as"
                            " darkness gradually falls over the forest clearing"
                            " surrounding them."
                        ),
                        "start_image_prompt": (
                            "Young Hansel and Young Gretel standing together side by"
                            " side in a dark forest clearing at dusk. Young Hansel is"
                            " positioned on the left holding a small cloth bundle"
                            " against his chest with both hands, while Young Gretel"
                            " stands on the right looking worried with her arms wrapped"
                            " around herself. The core subjects are Young Hansel and"
                            " Young Gretel from their respective images. The"
                            " environment around them is a dense medieval forest with"
                            " tall ancient trees and dim atmospheric lighting filtering"
                            " through the canopy above."
                        ),
                        "start_image_people_and_props_names": (
                            "Young Hansel,Young Gretel"
                        ),
                        "timestamp": 0,
                        "narrator_script": (
                            "A woodcutter abandoned his children in the dark forest."
                        ),
                    },
                    {
                        "video_prompt": (
                            "Young Hansel slowly bends down at the waist and drops"
                            " small white breadcrumbs along the narrow forest path"
                            " behind him as he walks forward step by step. The camera"
                            " follows Young Hansel from behind maintaining a medium"
                            " distance, then smoothly pans left to show the small white"
                            " breadcrumbs disappearing deeper into the dense trees"
                            " ahead."
                        ),
                        "start_image_prompt": (
                            "Young Hansel standing alone on a narrow forest path,"
                            " looking down at his hand holding small white breadcrumbs"
                            " ready to drop them. The core subject is Young Hansel from"
                            " his image positioned center frame. The environment shows"
                            " a narrow dirt path winding through dense trees with"
                            " dappled sunlight filtering through the canopy above"
                            " creating patches of light and shadow on the forest floor"
                            " around him."
                        ),
                        "start_image_people_and_props_names": "Young Hansel",
                        "timestamp": 5,
                        "narrator_script": (
                            "Clever Hansel dropped breadcrumbs along the path to mark"
                            " their way home."
                        ),
                    },
                    {
                        "video_prompt": (
                            "Young Gretel shivers visibly and hugs herself tightly as"
                            " owls hoot softly in the distance. The fireflies begin to"
                            " glow brighter, floating gently upward through the dark"
                            " forest around her. The camera slowly tilts up toward the"
                            " moonlit canopy above where the owls sit perched on their"
                            " branches."
                        ),
                        "start_image_prompt": (
                            "Young Gretel sitting alone on a mossy log in the dark"
                            " forest at night, looking frightened with her knees pulled"
                            " up. The core subject is Young Gretel from her image"
                            " positioned slightly off center. Moonlight filters through"
                            " the tall trees creating eerie shadows around her."
                            " Fireflies float gently near the ground and owls perch"
                            " silently on branches above watching from the darkness."
                        ),
                        "start_image_people_and_props_names": "Young Gretel",
                        "timestamp": 10,
                        "narrator_script": (
                            "Hungry birds ate every single crumb, leaving them lost."
                        ),
                    },
                    {
                        "video_prompt": (
                            "Young Hansel and Young Gretel slowly walk forward toward"
                            " the Gingerbread House, their eyes wide with wonder as"
                            " they approach. Warm golden light emanates from the candy"
                            " windows of the Gingerbread House. The camera tracks"
                            " backward smoothly, keeping Young Hansel, Young Gretel,"
                            " and the Gingerbread House all visible in frame"
                            " throughout."
                        ),
                        "start_image_prompt": (
                            "Young Hansel and Young Gretel standing at the edge of a"
                            " forest clearing, looking amazed at the Gingerbread House"
                            " positioned in front of them. The core subjects are Young"
                            " Hansel and Young Gretel from their images standing side"
                            " by side on the left side of frame. The Gingerbread House"
                            " from its image occupies the right side of frame with its"
                            " candy decorations clearly visible."
                        ),
                        "start_image_people_and_props_names": (
                            "Young Hansel,Young Gretel,Gingerbread House"
                        ),
                        "timestamp": 15,
                        "narrator_script": (
                            "Through the trees they spotted a magical gingerbread"
                            " house."
                        ),
                    },
                    {
                        "video_prompt": (
                            "The Wicked Witch slowly turns toward Young Hansel and"
                            " Young Gretel with a sinister smile spreading across her"
                            " face, her eyes gleaming in the dim light. She gestures"
                            " invitingly toward the Wooden Cottage interior behind her"
                            " with one hand. The camera slowly pushes in on the Wicked"
                            " Witch's face as her expression becomes more menacing and"
                            " threatening."
                        ),
                        "start_image_prompt": (
                            "The Wicked Witch standing at the doorway of the Wooden"
                            " Cottage, arms spread wide in a welcoming gesture. Young"
                            " Hansel and Young Gretel stand before her looking hesitant"
                            " and uncertain. The core subject is the Wicked Witch from"
                            " her image positioned center frame with her arms"
                            " outstretched. Young Hansel and Young Gretel from their"
                            " images stand together to the left side of frame."
                        ),
                        "start_image_people_and_props_names": (
                            "Wicked Witch,Young Hansel,Young Gretel"
                        ),
                        "timestamp": 20,
                        "narrator_script": (
                            "A wicked witch lived there, luring children into her trap."
                        ),
                    },
                    {
                        "video_prompt": (
                            "The Wicked Witch slowly reaches toward Young Gretel with"
                            " both hands extended. Young Gretel suddenly shoves the"
                            " Wicked Witch backward with force using both arms, sending"
                            " the Wicked Witch stumbling into the open oven behind her."
                            " The camera shakes slightly with the impact of the shove,"
                            " then holds steady on Young Gretel's determined face."
                        ),
                        "start_image_prompt": (
                            "Young Gretel standing near a large stone oven inside the"
                            " Wooden Cottage interior. The Wicked Witch stands behind"
                            " Young Gretel reaching forward with both hands. The core"
                            " subjects are Young Gretel and the Wicked Witch from their"
                            " images. Young Gretel is positioned in front of the open"
                            " oven while the Wicked Witch looms behind her."
                        ),
                        "start_image_people_and_props_names": (
                            "Young Gretel,Wicked Witch"
                        ),
                        "timestamp": 25,
                        "narrator_script": (
                            "Gretel outsmarted the witch, shoving her into the oven."
                        ),
                    },
                    {
                        "video_prompt": (
                            "Young Hansel and Young Gretel run joyfully away from the"
                            " Gingerbread House, bouncing slightly with excitement as"
                            " they move forward while carrying their small treasure"
                            " bags filled with gold coins. They look back once over"
                            " their shoulders with triumphant smiles before continuing"
                            " forward together. The camera pans right smoothly"
                            " following Young Hansel and Young Gretel's movement"
                            " through the sunlit forest path ahead of them."
                        ),
                        "start_image_prompt": (
                            "Young Hansel and Young Gretel running out of the"
                            " Gingerbread House carrying small treasure bags filled"
                            " with gold coins. The core subjects are Young Hansel and"
                            " Young Gretel from their images positioned side by side in"
                            " center frame on a sunlit forest path. Sunlight streams"
                            " through the forest trees behind them creating a warm"
                            " golden glow."
                        ),
                        "start_image_people_and_props_names": (
                            "Young Hansel,Young Gretel"
                        ),
                        "timestamp": 30,
                        "narrator_script": (
                            "Free at last, they gathered treasures and ran home"
                            " together."
                        ),
                    },
                    {
                        "video_prompt": (
                            "Young Hansel and Young Gretel smile broadly as they"
                            " embrace tightly together in the warm light. Warm"
                            " firelight flickers across Young Hansel and Young Gretel's"
                            " faces creating dancing shadows on the walls. The camera"
                            " slowly pushes in on their happy reunion, ending on a"
                            " close-up of Young Hansel and Young Gretel's relieved"
                            " expressions."
                        ),
                        "start_image_prompt": (
                            "Young Hansel and Young Gretel standing together inside the"
                            " Wooden Cottage interior, embracing each other with joyful"
                            " expressions on their faces. The core subjects are Young"
                            " Hansel and Young Gretel from their images positioned"
                            " center frame. Warm firelight illuminates the simple"
                            " wooden cottage around them casting a golden glow."
                        ),
                        "start_image_people_and_props_names": (
                            "Young Hansel,Young Gretel"
                        ),
                        "timestamp": 35,
                        "narrator_script": (
                            "Reunited with their father, they lived happily ever after."
                        ),
                    },
                ],
                "people_and_props": [
                    {
                        "name": "Young Hansel",
                        "prompt": (
                            "A young boy around 8 years old dressed in a tattered"
                            " medieval peasant costume with a rough brown tunic and"
                            " patched trousers, standing against a flat black"
                            " background. His light brown hair is slightly messy, his"
                            " blue eyes wide and innocent. The composition is a full"
                            " body shot captured with a 50mm lens at eye level. Soft"
                            " diffused lighting illuminates his face naturally."
                            " Photorealistic digital illustration style reminiscent of"
                            " classic fairy tale book illustrations."
                        ),
                    },
                    {
                        "name": "Young Gretel",
                        "prompt": (
                            "A young girl around 6 years old dressed in a simple"
                            " medieval peasant costume with a faded blue dress and"
                            " white apron, standing against a flat black background."
                            " Her golden blonde hair is tied with a red ribbon, her"
                            " green eyes bright and curious. The composition is a full"
                            " body shot captured with a 50mm lens at eye level. Soft"
                            " diffused lighting illuminates her face naturally."
                            " Photorealistic digital illustration style reminiscent of"
                            " classic fairy tale book illustrations."
                        ),
                    },
                    {
                        "name": "Wicked Witch",
                        "prompt": (
                            "An elderly woman dressed as a wicked witch costume with a"
                            " tattered black robe, pointed hat, and crooked wooden"
                            " staff, standing against a flat black background. Her"
                            " wrinkled face has sharp features, bushy gray eyebrows,"
                            " and a sinister expression. The composition is a full body"
                            " shot captured with a 50mm lens at eye level. Dramatic"
                            " side lighting creates deep shadows emphasizing her"
                            " menacing appearance. Photorealistic digital illustration"
                            " style reminiscent of classic fairy tale book"
                            " illustrations."
                        ),
                    },
                    {
                        "name": "Gingerbread House",
                        "prompt": (
                            "A whimsical gingerbread house structure made entirely of"
                            " cookies, candy, and icing decorations, standing against a"
                            " flat black background. The roof is covered with chocolate"
                            " shingles, windows are made of clear sugar glass, and"
                            " colorful candies decorate the walls. The composition"
                            " shows the full structure captured with a 35mm lens from a"
                            " slightly low angle. Warm golden lighting highlights the"
                            " sugary textures. Photorealistic digital illustration"
                            " style reminiscent of classic fairy tale book"
                            " illustrations."
                        ),
                    },
                    {
                        "name": "Wooden Cottage",
                        "prompt": (
                            "A simple rustic wooden cottage interior with stone"
                            " fireplace, wooden beams on the ceiling, and warm"
                            " firelight casting golden glow throughout the room,"
                            " standing against a flat black background. The composition"
                            " shows the full interior space captured with a 35mm lens"
                            " from eye level. Warm amber lighting creates cozy"
                            " atmosphere. Photorealistic digital illustration style"
                            " reminiscent of classic fairy tale book illustrations."
                        ),
                    },
                ],
            }
        )
    )
