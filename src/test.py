from pathlib import Path

from weekend_short_generation.tasks.video_parts_generator.video_parts_generator import (
    run_comfyui_workflow,
)

if __name__ == "__main__":

    workflow_file = "wan2_2_t2v_lightx2v_lora_distorch.json"

    def positive_prompt_modification(node):
        node["inputs"]["text"] = (
            "An ugly man dressed all in dirty brown clothes farts in an elevator,"
            " causing a group of professionally dressed people to look at him in"
            " disgust."
        )
        print(f"new prompt: {node['inputs']['text']}")
        return node

    def negative_prompt_modification(node):
        node["inputs"]["text"] = (
            "Static, person not moving, static scene, blurred, deformed hands, extra"
            " fingers, low quality, CGI look, cartoon, anime, static background, bad"
            " anatomy, slow motion, serious tone, dark lighting, watermark, text,"
            " signature."
        )
        print(f"new prompt: {node['inputs']['text']}")
        return node

    prompt_modifications = {
        "3": positive_prompt_modification,
        "4": negative_prompt_modification,
    }

    output_file_path = Path(__file__).parent.resolve() / "test_output_video.mp4"

    run_comfyui_workflow(workflow_file, output_file_path, prompt_modifications)
