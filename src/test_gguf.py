import os
from pathlib import Path

import torch
from diffusers import (
    GGUFQuantizationConfig,
    WanImageToVideoPipeline,
    WanTransformer3DModel,
)
from diffusers.utils import export_to_video, load_image

REPO_ROOT = Path(__file__).resolve().parent.parent
WAN_ROOT = REPO_ROOT / "src" / "services" / "Wan2.1"
DEFAULT_GGUF_PATH = (
    WAN_ROOT / "Wan2.1-I2V-14B-480P-gguf" / "wan2.1-i2v-14b-480p-Q4_K_S.gguf"
)
DEFAULT_MODEL_PATH = WAN_ROOT / "Wan2.1-I2V-14B-480P-Diffusers"
DEFAULT_INPUT_IMAGE = WAN_ROOT / "examples" / "i2v_input.JPG"


def resolve_existing_path(
    env_var_name: str, default_path: Path, description: str
) -> Path:
    candidate = Path(os.environ.get(env_var_name, default_path)).expanduser()
    if not candidate.exists():
        raise FileNotFoundError(
            f"Could not find {description} at: {candidate}. "
            f"Set {env_var_name} to override the default path."
        )
    return candidate


# 1. Configuration & Local Paths
local_gguf_path = resolve_existing_path("WAN_GGUF_PATH", DEFAULT_GGUF_PATH, "GGUF file")
local_model_path = resolve_existing_path(
    "WAN_DIFFUSERS_PATH", DEFAULT_MODEL_PATH, "Wan diffusers model directory"
)
input_image_path = resolve_existing_path(
    "WAN_INPUT_IMAGE", DEFAULT_INPUT_IMAGE, "input image"
)

# Define VRAM allocations to split the model across both RTX 5070s
device_map = "balanced"
max_memory = {0: "14GB", 1: "14GB"}

# 2. Load the Transformer locally from the GGUF file
print(f"Loading quantized transformer from local file: {local_gguf_path}...")
transformer = WanTransformer3DModel.from_single_file(
    str(local_gguf_path),
    quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
    torch_dtype=torch.bfloat16,
    device_map=device_map,
    max_memory=max_memory,
)

# 3. Assemble the Pipeline
print("Assembling WanImageToVideoPipeline...")
# The pipeline structure configuration is fetched from the base hub layout,
# but we override the transformer with our locally loaded GGUF instance.
pipe = WanImageToVideoPipeline.from_pretrained(
    str(local_model_path),
    transformer=transformer,
    torch_dtype=torch.bfloat16,
    device_map=device_map,
    max_memory=max_memory,
)

# Performance tweaks for dual-GPU VRAM overhead
pipe.vae.enable_tiling()
pipe.vae.enable_slicing()

# 4. Input Processing
init_image = load_image(str(input_image_path)).convert("RGB").resize((832, 480))
prompt = "Cinematic slow motion camera pan, hyperrealistic details, 4k resolution"
negative_prompt = "blurry, low quality, distorted"

# 5. Execution Loop
print("Running model inference across both RTX 5070 GPUs...")
with torch.inference_mode():
    video_frames = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=init_image,
        num_frames=81,  # Wan2.1 native frame length
        height=480,
        width=832,
        num_inference_steps=40,
        guidance_scale=6.0,
    ).frames[0]

# 6. Save the video file
output_video_path = REPO_ROOT / "local_model_output.mp4"
print(f"Encoding frames into {output_video_path}...")
export_to_video(video_frames, str(output_video_path), fps=16)

print("Process finished successfully!")
