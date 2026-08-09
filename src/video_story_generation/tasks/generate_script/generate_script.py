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


VIDEO_LENGTH = 60  # seconds
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
        diff1 = list(set(list(person_and_prop_item.keys())) ^ set(["name", "prompt"]))
        if diff1 != []:
            error_text = (
                f"Error: Person/Prop {person_and_prop_i} has invalid keys. Key diff ="
                f" {diff1} Expected keys are: {{'name', 'prompt'}}"
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

        if len(person_and_prop_item["name"].split(" ")) < 2:
            error_text = (
                f"Error: Person or prop '{person_and_prop_item['name']}' is too short."
                " Please provide a more detailed name with at least 2 words."
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

        if len(segment["start_image_prompt"].split(" ")) > 120:
            error_text = (
                f"Error: The Start image prompt for segment {segment_i} is too long."
                " Please shorten the prompt to less than 120 words."
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

        if len(segment["video_prompt"].split(" ")) < 40:
            error_text = (
                f"Error: Video prompt for segment {segment_i} is too short. Please"
                " provide a more detailed prompt with more than 40 words."
            )
            print(error_text)
            res += error_text + "\n"

        if len(segment["video_prompt"].split(" ")) > 120:
            error_text = (
                f"Error: Video prompt for segment {segment_i} is too long. Please"
                " shorten the prompt to less than 120 words."
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

    for segment_i, segment in enumerate(video_segment_list):

        if ENABLE_AUDIO_DURATION_CHECK:
            duration = generate_audio_file_get_duration(
                segment["narrator_script"],
                file_path=f"data/audio/temp_audio_file_{segment_i}.wav",
            )
        else:
            duration = estimate_narrator_duration_seconds(segment["narrator_script"])

        if abs((duration - SEGMENT_LENGTH) / SEGMENT_LENGTH) > 0.20:
            error_text = (
                f"Error: Narrator script for segment {segment_i} has a duration of"
                f" {duration:.2f} seconds, which exceeds the allowed 20% variance from"
                f" the expected {SEGMENT_LENGTH} seconds."
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
    I am designing a video story. I have a start image prompt and a video prompt. The start image prompt describes the initial scene, while the video prompt describes the subsequent action. I want to ensure that the start image prompt is referring to the same objects, characters, and props as the video prompt.
    
    Start image prompt can describe objects and props that are not present in the video prompt, but the video prompt should not introduce any new objects, characters, or props that are not already present in the start image prompt.
    
    I want to ensure that the start image prompt is referring to the same objects, characters, and props as the video prompt.
    
    Make sure that all objects are referred to in the same way in both prompts. For example, if the start image prompt refers to "young boy Hansel" and the video prompt refers to "Hansel", 
    this is a non-matching reference and include it in your output under non_matching_objects_or_persons. 
    If the start image prompt refers to "wooden cage" and the video prompt refers to "cage", 
    this is a non-matching reference and include it in your output under non_matching_objects_or_persons. 
    If the start image prompt refers to "Wicked Witch" and the video prompt refers to "Wicked Witch", 
    this is a matching reference and should NOT be included in your output under non_matching_objects_or_persons.
    
    Return JSON with the following structure:
    {{
        "non_matching_objects_or_persons": [
            {{
                "name": str,
                "reason": str
            }},
            ...
        ]
    }}
    Only return the JSON object. Do not include any additional text or explanations. If all props are present, return an empty list for "non_matching_objects_or_persons".

    If there are no non-matching objects or persons, return:
    {{
        "non_matching_objects_or_persons": []
    }}
    
    Start Image Prompt: {start_image_prompt}
    
    Video Prompt: {video_prompt}
    
    """

    res = ollama.chat(
        model="qwen3.6:27b",
        messages=[{"role": "user", "content": llm_prompt}],
        format="json",  # Forces JSON response
        # options={
        #     "temperature": 0,  # Zero variance for speed and determinism
        #     "num_predict": 350,  # Stops inference early to prevent runaway generation
        # },
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
    Look for all items in the start_image_prompt for references to objects that appear more than once and should be
    props. Then compare those objects to the list of people_and_props to ensure that they are included. If any are missing, return an error message.

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
    Task: Find objects referenced in 2 or more segments that are missing from `props_list`.

    Return JSON format:
    {{
    "missing_props": [
        {{ "prop_name": "<string>", "segment_index": <int>, "reason": "<string>" }}
    ]
    }}
    
    If you find no missing props, return:
    {{ "missing_props": [] }}

    segments:
    {start_image_prompts}

    props_list:
    {', '.join([p['name'] for p in people_and_props])}
    
    """
    print(f"LLM Prompt for checking start image prompt props: {llm_prompt}")

    res = ollama.chat(
        model="qwen3.6:27b",
        messages=[{"role": "user", "content": llm_prompt}],
        format="json",  # Forces JSON response
        # options={
        #     "temperature": 0,  # Zero variance for speed and determinism
        #     # "num_predict": 350,  # Stops inference early to prevent runaway generation
        # },
        # ": 64 * 1024},  # Adjust based on your memory needs (Default 262k is VRAM heavy)
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

    Args:
        segment (dict): A video segment containing a start image prompt and a video prompt.

    Returns:
        str: "success" if validation passes, otherwise an error message.
    """

    llm_prompt = f"""
    Task: Verify that the start image prompt describes the initial scene and the video prompt describes the subsequent action. Ensure that all objects, characters, and props mentioned in the video prompt are also present in the start image prompt. Identify and list any inconsistencies or missing references between the two prompts.

    Return JSON format:
    {{
    "inconsistencies": [
        {{ "reason": "<string>" }}
    ]
    }}
    
    If you find no missing props, return:
    {{ "inconsistencies": [] }}

    start_image_prompt:
    {segment['start_image_prompt']}
    video_prompt:
    {segment['video_prompt']}
    
    """
    print(f"LLM Prompt for checking start image prompt props: {llm_prompt}")

    res = ollama.chat(
        model="qwen3.6:27b",
        messages=[{"role": "user", "content": llm_prompt}],
        format="json",  # Forces JSON response
        # options={
        #     "temperature": 0,  # Zero variance for speed and determinism
        #     # "num_predict": 350,  # Stops inference early to prevent runaway generation
        # },
        # ": 64 * 1024},  # Adjust based on your memory needs (Default 262k is VRAM heavy)
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
            error_messages.append(f"Error: {inconsistency['reason']}")
        return "\n".join(error_messages)


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

    json_output_path = f"data/script_{video_id}.json"
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
                "people_and_props": [
                    {
                        "name": "Young Boy Hansel",
                        "prompt": (
                            "A young boy around 8 years old dressed in a simple"
                            " medieval peasant costume with a brown tunic and leather"
                            " belt, standing against a flat black background. The"
                            " character has light brown hair and wears simple wooden"
                            " sandals. Photorealistic style with natural lighting that"
                            " highlights the texture of the fabric and the youthful"
                            " features of the child."
                        ),
                    },
                    {
                        "name": "Young Girl Gretel",
                        "prompt": (
                            "A young girl around 7 years old dressed in a simple"
                            " medieval peasant costume with a blue dress and white"
                            " apron, standing against a flat black background. The"
                            " character has blonde hair tied with a red ribbon and"
                            " wears simple cloth shoes. Photorealistic style with"
                            " natural lighting that highlights the texture of the"
                            " fabric and the innocent features of the child."
                        ),
                    },
                    # {
                    #     "name": "Wicked Witch Character",
                    #     "prompt": "An elderly woman dressed as a wicked witch costume with a pointed black hat, dark purple robe, and crooked wooden staff. The character has wrinkled skin, wild gray hair, and wears heavy boots. Standing against a flat black background. Photorealistic style with dramatic lighting that emphasizes the sinister expression and textured costume details."
                    # },
                    # {
                    #     "name": "Gingerbread Candy House",
                    #     "prompt": "A whimsical gingerbread house made entirely of colorful candies, cookies, and icing decorations. The structure features chocolate shingles, gumdrop windows, lollipop door handles, and candy cane pillars. Standing against a flat black background. Photorealistic style with bright lighting that makes the sweets appear glossy and appetizing."
                    # },
                    # {
                    #     "name": "Dark Forest Setting",
                    #     "prompt": "A dense, mysterious forest scene with tall twisted trees, thick fog on the ground, and dappled sunlight filtering through the canopy. The path is covered with fallen leaves and mushrooms grow among the roots. Standing against a flat black background. Photorealistic style with moody lighting that creates an eerie atmosphere."
                    # },
                    # {
                    #     "name": "Wooden Cage Prop",
                    #     "prompt": "A rustic wooden cage made of rough-hewn logs with iron reinforcements, standing against a flat black background. The cage has bars spaced closely together and shows signs of age and wear. Photorealistic style with dramatic side lighting that emphasizes the texture of the wood and metal."
                    # }
                ],
                "video_segments": [
                    {
                        "narrator_script": (
                            "Lost deep in the dark forest, young Hansel and Gretel"
                            " wandered alone after being abandoned by their cruel"
                            " stepmother who wanted to get rid of them."
                        ),
                        "start_image_people_and_props_names": (
                            "Young Boy Hansel,Young Girl Gretel,Dark Forest Setting"
                        ),
                        "start_image_prompt": (
                            "The Young Boy Hansel and Young Girl Gretel are standing"
                            " together in the Dark Forest Setting, looking lost and"
                            " frightened. The two small children appear tiny surrounded"
                            " by towering twisted trees with fog swirling around their"
                            " feet. Hansel holds a small bundle of sticks while Gretel"
                            " clutches his arm tightly."
                        ),
                        "timestamp": 0,
                        "video_prompt": (
                            "The camera slowly pushes in toward the two frightened"
                            " children as they look around nervously in all directions."
                            " Hansel drops breadcrumbs from his pocket onto the forest"
                            " floor while Gretel clutches his arm tighter. The fog"
                            " swirls gently around them and leaves rustle in the wind"
                            " creating an eerie atmosphere."
                        ),
                    },
                    {
                        "narrator_script": (
                            "But their hunger led them to discover something magical -"
                            " a wonderful house made entirely of sweets and treats that"
                            " filled their empty bellies."
                        ),
                        "start_image_people_and_props_names": (
                            "Young Boy Hansel,Young Girl Gretel,Gingerbread Candy House"
                        ),
                        "start_image_prompt": (
                            "The Young Boy Hansel and Young Girl Gretel stand before"
                            " the Gingerbread Candy House with wide eyes full of"
                            " wonder. The magical house sparkles with colorful candies,"
                            " gumdrop windows, and lollipop decorations that catch the"
                            " light beautifully."
                        ),
                        "timestamp": 5,
                        "video_prompt": (
                            "The children slowly approach the candy house with hesitant"
                            " steps, reaching out to touch the sweet decorations on the"
                            " walls. Gretel picks up a dropped candy from the ground"
                            " while Hansel examines the gumdrop windows with amazement"
                            " as their stomachs growl loudly."
                        ),
                    },
                    {
                        "narrator_script": (
                            "But the house belonged to a wicked witch who wanted to eat"
                            " them! She imprisoned Hansel and made poor Gretel her"
                            " helpless servant."
                        ),
                        "start_image_people_and_props_names": (
                            "Wicked Witch Character,Young Boy Hansel,Young Girl Gretel"
                        ),
                        "start_image_prompt": (
                            "The Wicked Witch Character stands menacingly before the"
                            " Young Boy Hansel and Young Girl Gretel at the door of the"
                            " Gingerbread Candy House. The children look terrified as"
                            " the witch reaches for them with her gnarled hands."
                        ),
                        "timestamp": 10,
                        "video_prompt": (
                            "The wicked witch grabs Hansel forcefully and throws him"
                            " into the Wooden Cage Prop while forcing Gretel to become"
                            " her servant in the kitchen. The witch cackles evilly, her"
                            " staff casting dark shadows across the room as she locks"
                            " the cage door."
                        ),
                    },
                    {
                        "narrator_script": (
                            "The evil witch kept checking if Hansel was fat enough to"
                            " eat, but clever Hansel tricked her by holding up a bone"
                            " instead of his finger."
                        ),
                        "start_image_people_and_props_names": (
                            "Young Boy Hansel,Wicked Witch Character,Wooden Cage Prop"
                        ),
                        "start_image_prompt": (
                            "The Young Boy Hansel sits inside the Wooden Cage Prop"
                            " looking sad and trapped while the Wicked Witch Character"
                            " peeks through the bars checking if he has grown fat"
                            " enough."
                        ),
                        "timestamp": 15,
                        "video_prompt": (
                            "The witch repeatedly reaches through the cage bars to feel"
                            " Hansel's thin finger, checking if he has grown fat enough"
                            " to eat. Hansel cleverly holds up a small bone instead of"
                            " his finger each time, tricking the blind witch."
                        ),
                    },
                    {
                        "narrator_script": (
                            "But clever Gretel outsmarted her! When the blind witch"
                            " asked her to check the oven, she pushed the evil"
                            " sorceress inside instead!"
                        ),
                        "start_image_people_and_props_names": (
                            "Wicked Witch Character,Young Girl Gretel"
                        ),
                        "start_image_prompt": (
                            "The Wicked Witch Character stands before a large stone"
                            " oven while the Young Girl Gretel stands nearby pretending"
                            " to be confused about how to check if it is hot enough."
                        ),
                        "timestamp": 20,
                        "video_prompt": (
                            "The witch demonstrates how to peek into the oven, leaning"
                            " forward with her poor eyesight. Instead of checking,"
                            " Gretel suddenly pushes the witch forcefully into the"
                            " flames! The witch falls backward screaming as the heavy"
                            " oven door slams shut behind her."
                        ),
                    },
                    {
                        "narrator_script": (
                            "Free at last! The brave siblings escaped with the witch's"
                            " precious treasures and began their journey home through"
                            " the enchanted forest."
                        ),
                        "start_image_people_and_props_names": (
                            "Young Boy Hansel,Young Girl Gretel"
                        ),
                        "start_image_prompt": (
                            "The Young Boy Hansel and Young Girl Gretel stand together"
                            " outside the Gingerbread Candy House with the Wooden Cage"
                            " Prop now open. The children look relieved and free as"
                            " they gather treasures from the witch's house."
                        ),
                        "timestamp": 25,
                        "video_prompt": (
                            "The freed siblings run joyfully out of the candy house,"
                            " collecting bags of gold coins and jewels from the witch's"
                            " treasure chest. They laugh and dance together,"
                            " celebrating their freedom as the camera pulls back to"
                            " show them escaping into the forest."
                        ),
                    },
                    {
                        "narrator_script": (
                            "They followed the breadcrumbs home, running through the"
                            " once-scary forest that now felt bright and welcoming"
                            " under the warm afternoon sun."
                        ),
                        "start_image_people_and_props_names": (
                            "Young Boy Hansel,Young Girl Gretel,Dark Forest Setting"
                        ),
                        "start_image_prompt": (
                            "The Young Boy Hansel and Young Girl Gretel run happily"
                            " along a sunlit path in the Dark Forest Setting, carrying"
                            " bags of treasure. The forest appears brighter and less"
                            " menacing now."
                        ),
                        "timestamp": 30,
                        "video_prompt": (
                            "The children run happily through the forest path, laughing"
                            " and dancing with their treasure bags bouncing on their"
                            " backs. The camera follows them as they emerge from the"
                            " dark trees into warm golden sunlight, finally safe and"
                            " free from danger."
                        ),
                    },
                    {
                        "narrator_script": (
                            "And so Hansel and Gretel found their way home to their"
                            " loving father, who had missed them terribly. They lived"
                            " happily ever after together."
                        ),
                        "start_image_people_and_props_names": (
                            "Young Boy Hansel,Young Girl Gretel"
                        ),
                        "start_image_prompt": (
                            "The Young Boy Hansel and Young Girl Gretel embrace their"
                            " loving father in a simple wooden cottage. The children"
                            " look happy and safe as they reunite with their family."
                        ),
                        "timestamp": 35,
                        "video_prompt": (
                            "The children run into their father's arms, hugging him"
                            " tightly as tears of joy flow down their faces. The camera"
                            " slowly pulls back showing the warm cottage interior with"
                            " a fire burning, ending on this heartwarming family"
                            " reunion scene."
                        ),
                    },
                ],
            }
        )
    )
