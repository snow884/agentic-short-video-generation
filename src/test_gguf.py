import os
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch
from diffusers import (
    GGUFQuantizationConfig,
    WanImageToVideoPipeline,
    WanTransformer3DModel,
)
from diffusers.utils import export_to_video, load_image


class AdjustableExecutionWanImageToVideoPipeline(WanImageToVideoPipeline):
    @property
    def _execution_device(self):
        override = getattr(self, "_execution_device_override", None)
        if override is not None:
            return override
        return super()._execution_device


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


def build_max_memory(
    reserve_gib: int = 2, allow_cpu_offload: bool = False
) -> dict[int | str, str]:
    if not torch.cuda.is_available() or torch.cuda.device_count() == 0:
        return {"cpu": "64GiB"}

    memory_budget: dict[int | str, str] = {}
    for device_index in range(torch.cuda.device_count()):
        total_gib = torch.cuda.get_device_properties(device_index).total_memory // (
            1024**3
        )
        usable_gib = max(1, total_gib - reserve_gib)
        memory_budget[device_index] = f"{usable_gib}GiB"

    if allow_cpu_offload:
        memory_budget["cpu"] = os.environ.get("WAN_CPU_MAX_MEMORY", "64GiB")
    return memory_budget


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
allow_cpu_offload = os.environ.get("WAN_ALLOW_CPU_OFFLOAD", "0") == "1"
reserve_gib = int(os.environ.get("WAN_GPU_RESERVE_GIB", "1"))
max_memory = build_max_memory(
    reserve_gib=reserve_gib,
    allow_cpu_offload=allow_cpu_offload,
)
use_max_memory = os.environ.get("WAN_USE_MAX_MEMORY", "0") == "1"
if use_max_memory:
    print(f"Using max_memory={max_memory}")
else:
    print("Using default accelerate memory placement (WAN_USE_MAX_MEMORY=0)")

# 2. Load the Transformer locally from the GGUF file
print(f"Loading quantized transformer from local file: {local_gguf_path}...")
transformer_load_kwargs = {}
if use_max_memory:
    transformer_load_kwargs["max_memory"] = max_memory

transformer = WanTransformer3DModel.from_single_file(
    str(local_gguf_path),
    quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
    torch_dtype=torch.bfloat16,
    device_map=device_map,
    **transformer_load_kwargs,
)

# 3. Assemble the Pipeline
print("Assembling WanImageToVideoPipeline...")
# The pipeline structure configuration is fetched from the base hub layout,
# but we override the transformer with our locally loaded GGUF instance.
pipeline_load_kwargs = {}
if use_max_memory:
    pipeline_load_kwargs["max_memory"] = max_memory

pipe = WanImageToVideoPipeline.from_pretrained(
    str(local_model_path),
    transformer=transformer,
    torch_dtype=torch.bfloat16,
    device_map=device_map,
    **pipeline_load_kwargs,
)
pipe.__class__ = AdjustableExecutionWanImageToVideoPipeline
pipe._execution_device_override = None
print(f"Pipeline execution device: {pipe._execution_device}")

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
    generation_kwargs = dict(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=init_image,
        num_frames=81,  # Wan2.1 native frame length
        height=480,
        width=832,
        num_inference_steps=40,
        guidance_scale=6.0,
    )
    try:
        video_frames = pipe(**generation_kwargs).frames[0]
    except RuntimeError as error:
        error_text = str(error)
        mixed_device_error = (
            "Expected all tensors to be on the same device" in error_text
            or "weight type (CPUBFloat16Type)" in error_text
        )
        if not mixed_device_error:
            raise

        print(
            "Detected mixed CPU/GPU dispatch at runtime; retrying with CPU staging "
            "while keeping sharded modules on GPUs."
        )
        pipe._execution_device_override = torch.device("cpu")
        torch.cuda.empty_cache()
        video_frames = pipe(**generation_kwargs).frames[0]

# 6. Save the video file
output_video_path = REPO_ROOT / "local_model_output.mp4"
print(f"Encoding frames into {output_video_path}...")
export_to_video(video_frames, str(output_video_path), fps=16)

print("Process finished successfully!")
