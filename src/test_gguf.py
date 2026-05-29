import os
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


REPO_ROOT = Path(__file__).resolve().parent.parent
WAN_ROOT = REPO_ROOT / "src" / "services" / "Wan2.1"
DEFAULT_GGUF_PATH = (
    WAN_ROOT / "Wan2.1-I2V-14B-480P-gguf" / "wan2.1-i2v-14b-480p-Q4_K_S.gguf"
)
DEFAULT_MODEL_PATH = WAN_ROOT / "Wan2.1-I2V-14B-480P-Diffusers"
DEFAULT_INPUT_IMAGE = WAN_ROOT / "examples" / "i2v_input.JPG"


import os

import torch
from diffusers import WanVideoPipeline
from diffusers.utils import export_to_video, load_image
from transformers import T5EncoderModel, T5Tokenizer

# 1. Setup paths and device
# Note: Ensure you have downloaded the Wan2.1-I2V-14B-480P-gguf file
# and the matching text encoder (usually T5-v1.1-XXL)
model_dir = DEFAULT_MODEL_PATH
device = "cuda" if torch.cuda.is_available() else "cpu"

print("Initializing text encoders...")
tokenizer = T5Tokenizer.from_pretrained("google/t5-v1.1-xxl")
text_encoder = T5EncoderModel.from_pretrained(
    "google/t5-v1.1-xxl", torch_dtype=torch.bfloat16
)

# 2. Load the Wan2.1 Pipeline
# (Depending on the exact diffusers integration, you may need a custom GGUF loader class)
print("Loading Wan2.1 I2V GGUF Model...")
pipeline = WanVideoPipeline.from_pretrained(
    model_dir,
    text_encoder=text_encoder,
    tokenizer=tokenizer,
    torch_dtype=torch.bfloat16,
)
pipeline.to(device)

# Enable memory optimizations if running on consumer hardware (highly recommended for 14B)
pipeline.enable_model_cpu_offload()
# pipeline.enable_vae_slicing()

# 3. Prepare Input Image and Prompt
# The image should ideally match the 480p target aspect ratio (e.g., 832x480 or 480x832)
input_image_path = DEFAULT_INPUT_IMAGE
image = load_image(input_image_path).convert("RGB")

prompt = (
    "A cinematic shot of a dragon breathing fire, smooth motion, high definition, 4k"
    " resolution"
)
negative_prompt = "blurry, low quality, distorted, static, jittery"

print("Generating video frames...")
# 4. Run Inference
with torch.inference_mode():
    video_frames = pipeline(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=image,
        num_frames=81,  # Wan2.1 standard frame count for smooth video
        height=480,  # Fixed for the 480P model
        width=832,  # Adjustable based on aspect ratio
        num_inference_steps=40,  # Standard steps for Wan2.1 flow matching
        guidance_scale=6.0,  # Classifier-free guidance strength
    ).frames[0]

# 5. Export to MP4
output_video_path = "wan21_generated_video.mp4"
print(f"Saving video to {output_video_path}...")
export_to_video(video_frames, output_video_path, fps=16)
print("Done!")
