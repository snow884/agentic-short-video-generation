from weekend_short_generation.tasks.video_parts_generator.video_parts_generator import (
    run_comfyui_workflow,
)


def generate_video(prompt, output_file_path):

    workflow_file = "wan2_2_t2v_lightx2v_lora_distorch.json"

    def positive_prompt_modification(node):
        node["inputs"]["text"] = prompt
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

    run_comfyui_workflow(workflow_file, output_file_path, prompt_modifications)
