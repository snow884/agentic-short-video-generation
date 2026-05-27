import os

import torch
from diffusers import (
    AutoencoderKLWan,
    GGUFQuantizationConfig,
    WanImageToVideoPipeline,
    WanTransformer3DModel,
)
from diffusers.utils import export_to_video, load_image
from transformers import AutoTokenizer, T5EncoderModel

# 1. Device and allocator setup
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

local_model_path = "./src/services/Wan2.1/Wan2.1-I2V-14B-480P-Diffusers/"
GGUF_FILE_PATH = (
    "./src/services/Wan2.1/Wan2.1-I2V-14B-480P-gguf/wan2.1-i2v-14b-480p-Q4_K_S.gguf"
)
prompt = "A cinematic shot of a white cat."

# ==========================================
# STEP 1: EXTRACT EMBEDDINGS ENTIRELY ON CPU
# ==========================================
print("Loading Text Encoder onto CPU to extract prompt embeddings...")
tokenizer = AutoTokenizer.from_pretrained(local_model_path, subfolder="tokenizer")

# Load in float16/bfloat16 directly to CPU (no bitsandbytes needed since RAM handles this easily)
text_encoder = T5EncoderModel.from_pretrained(
    local_model_path,
    subfolder="text_encoder",
    torch_dtype=torch.bfloat16,
    device_map={"": "cpu"},
    local_files_only=True,
)

print("Encoding prompt text...")
with torch.no_grad():
    text_inputs = tokenizer(
        prompt,
        padding="max_length",
        max_length=512,  # Wan2.1 default context length
        truncation=True,
        return_tensors="pt",
    )

    # Generate positive embeddings
    prompt_embeds = text_encoder(text_inputs.input_ids)[0]

    # Generate negative/unconditional embeddings (Wan uses empty string negative prompts)
    uncond_inputs = tokenizer(
        "",
        padding="max_length",
        max_length=512,
        truncation=True,
        return_tensors="pt",
    )
    negative_prompt_embeds = text_encoder(uncond_inputs.input_ids)[0]

# Completely purge the text encoder from RAM to keep system clean
del text_encoder
import gc

gc.collect()
print("Prompt successfully compiled! Text encoder cleared.")

# ==========================================
# STEP 2: LAUNCH GPU INFRASTRUCTURE
# ==========================================
print("Loading Quantized Transformer onto cuda:0...")
transformer = WanTransformer3DModel.from_single_file(
    GGUF_FILE_PATH,
    quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
    torch_dtype=torch.bfloat16,
    local_files_only=True,
).to("cuda:0")

print("Loading supporting components...")
vae = AutoencoderKLWan.from_pretrained(
    local_model_path, subfolder="vae", torch_dtype=torch.bfloat16, local_files_only=True
)

# 4. Initialize pipeline PASSING None TO THE TEXT ENCODER
pipe = WanImageToVideoPipeline.from_pretrained(
    local_model_path,
    transformer=transformer,
    text_encoder=None,  # Pass None since we already have the embeddings!
    vae=vae,
    torch_dtype=torch.bfloat16,
)

# 5. Offload remaining components (VAE, Image Encoder) dynamically to GPU 1
print("Registering offloading hooks for GPU 1...")
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
        # We pass the pre-computed embeddings directly into the pipeline execution
        video = pipe(
            prompt_embeds=prompt_embeds,
            negative_prompt_embeds=negative_prompt_embeds,
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
