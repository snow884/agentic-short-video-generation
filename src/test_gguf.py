import os

import torch
from diffusers import (
    AutoencoderKLWan,
    GGUFQuantizationConfig,
    WanImageToVideoPipeline,
    WanTransformer3DModel,
)
from diffusers.utils import export_to_video, load_image
from transformers import CLIPVisionModel

# 1. Prevent memory fragmentation at the CUDA allocator level
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

local_model_path = "./src/services/Wan2.1/Wan2.1-I2V-14B-480P-Diffusers/"
GGUF_FILE_PATH = (
    "./src/services/Wan2.1/Wan2.1-I2V-14B-480P-gguf/wan2.1-i2v-14b-480p-Q4_K_S.gguf"
)

# 2. Load Image Encoder onto GPU 1
print("Loading Image Encoder onto cuda:1...")
image_encoder = CLIPVisionModel.from_pretrained(
    local_model_path,
    subfolder="image_encoder",
    torch_dtype=torch.bfloat16,
    local_files_only=True,
).to("cuda:1")
image_encoder.gradient_checkpointing_enable()

# 3. FIX: Cast VAE to bfloat16 instead of float32 to instantly save ~2.5GB of VRAM on GPU 1
print("Loading VAE onto cuda:1 in bfloat16...")
vae = AutoencoderKLWan.from_pretrained(
    local_model_path,
    subfolder="vae",
    torch_dtype=torch.bfloat16,  # Changed from float32 to bfloat16
    local_files_only=True,
).to("cuda:1")

# 4. Load the heavy 14B GGUF Transformer onto GPU 0
print("Loading Quantized Transformer onto cuda:0...")
transformer = WanTransformer3DModel.from_single_file(
    GGUF_FILE_PATH,
    quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
    torch_dtype=torch.bfloat16,
    local_files_only=True,
).to("cuda:0")

# 5. Initialize pipeline
pipe = WanImageToVideoPipeline.from_pretrained(
    local_model_path,
    transformer=transformer,
    vae=vae,
    image_encoder=image_encoder,
    torch_dtype=torch.bfloat16,
)

# 6. Push Text Encoders to GPU 1 explicitly
if hasattr(pipe, "text_encoder"):
    pipe.text_encoder.to("cuda:1")
if hasattr(pipe, "text_encoder_2"):
    pipe.text_encoder_2.to("cuda:1")

# 7. CRITICAL MEMORY OPTIMIZATIONS FOR GPU 1
pipe.vae.enable_tiling()
pipe.vae.enable_slicing()
pipe.enable_attention_slicing()

# FIX: Force GPU 1 components to offload memory sequentially if they overlap
# Using device_map or component-level offloading handles the text-to-image encoder handoff
pipe.enable_model_cpu_offload(gpu_id=1)

# Generate video
image = load_image(
    "src/services/Wan2.1/Wan2.1-I2V-14B-480P-Diffusers/examples/i2v_input.JPG"
)

print("Starting generation loop...")
# Clear cache before starting the heavy inference loop
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
