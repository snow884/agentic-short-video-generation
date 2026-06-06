from pathlib import Path

from weekend_short_generation.tasks.video_parts_generator.video_parts_generator import (
    run_comfyui_workflow,
)

if __name__ == "__main__":

    workflow_file = "wan2_2_t2v_lightx2v_lora_distorch.json"

    def positive_prompt_modification(node):
        node["inputs"]["prompt"] = (
            " A bustling city street during a vibrant festival, with colorful"
            " decorations, lively crowds, and a festive atmosphere. The scene is filled"
            " with energy and excitement, capturing the essence of a joyful celebration"
            " in an urban setting."
        )
        return node

    def negative_prompt_modification(node):
        node["inputs"]["prompt"] = (
            "blurry, low quality, distorted, deformed, bad anatomy, disfigured, poorly"
            " drawn face, mutation, mutated, extra limbs, ugly"
        )
        return node

    prompt_modifications = {
        "3": positive_prompt_modification,
        "4": negative_prompt_modification,
    }

    output_file_path = Path(__file__).parent.resolve() / "test_output_video.mp4"

    run_comfyui_workflow(workflow_file, output_file_path, prompt_modifications)
