import os

import torch
from diffusers import (
    AutoencoderKLWan,
    GGUFQuantizationConfig,
    WanImageToVideoPipeline,
    WanTransformer3DModel,
)
from diffusers.utils import export_to_video, load_image
from transformers import T5EncoderModel

# 1. Device and allocator setup
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

local_model_path = "./src/services/Wan2.1/Wan2.1-I2V-14B-480P-Diffusers/"
GGUF_FILE_PATH = (
    "./src/services/Wan2.1/Wan2.1-I2V-14B-480P-gguf/wan2.1-i2v-14b-480p-Q4_K_S.gguf"
)

# 2. Load the main heavy Transformer directly to GPU 0
print("Loading Quantized Transformer onto cuda:0...")
transformer = WanTransformer3DModel.from_single_file(
    GGUF_FILE_PATH,
    quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
    torch_dtype=torch.bfloat16,
    local_files_only=True,
).to("cuda:0")

# 3. FIX: Load the massive text encoder in 8-bit precision or auto-mapped
# This shrinks the text encoder memory usage from ~11GB down to ~5.5GB!
# Note: Requires `pip install bitsandbytes acceleration` if not installed
print("Loading Text Encoder with bitsandbytes 8-bit optimization...")
text_encoder = T5EncoderModel.from_pretrained(
    local_model_path,
    subfolder="text_encoder",
    load_in_8bit=True,  # Compresses the encoder layers significantly
    device_map="auto",  # Dynamically utilizes remaining space across both cards
    local_files_only=True,
)

print("Loading supporting components...")
vae = AutoencoderKLWan.from_pretrained(
    local_model_path, subfolder="vae", torch_dtype=torch.bfloat16, local_files_only=True
)

# 4. Initialize pipeline
pipe = WanImageToVideoPipeline.from_pretrained(
    local_model_path,
    transformer=transformer,
    text_encoder=text_encoder,
    vae=vae,
    torch_dtype=torch.bfloat16,
)

# 5. Offload remaining components (VAE, Image Encoder) dynamically to GPU 1
print("Registering offloading hooks...")
pipe.enable_model_cpu_offload(gpu_id=1)

# Strict patch/tile-based memory optimizations
pipe.vae.enable_tiling()
pipe.vae.enable_slicing()
pipe.enable_attention_slicing()

# Generate video
image = load_image(
    "src/services/Wan2.1/Wan2.1-I2V-14B-480P-Diffusers/examples/i2v_input.JPG"
)

print("Starting generation loop...")
torch.cuda.empty_cache()

with torch.no_grad():
    with torch.backends.cuda.sdp_kernel(
        enable_flash=True, enable_math=False, enable_mem_efficient=True
    ):
        video = pipe(
            prompt="A cinematic shot of a white cat.",
            image=image,
            num_frames=81,
            height=480,
            width=832,
            num_inference_steps=40,
            guidance_scale=6.0,
        ).frames[0]

# Export result
export_to_video(video, "output.mp4", fps=16)
print("Video saved successfully!")
