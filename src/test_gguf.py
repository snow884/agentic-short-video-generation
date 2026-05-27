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
print("Loading Text Encoder onto CPU...")
tokenizer = AutoTokenizer.from_pretrained(local_model_path, subfolder="tokenizer")
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
        max_length=512,
        truncation=True,
        return_tensors="pt",
    )
    prompt_embeds = text_encoder(text_inputs.input_ids)[0]

    uncond_inputs = tokenizer(
        "", padding="max_length", max_length=512, truncation=True, return_tensors="pt"
    )
    negative_prompt_embeds = text_encoder(uncond_inputs.input_ids)[0]

del text_encoder
import gc

gc.collect()

# ==========================================
# STEP 2: LAUNCH BALANCED GPU ARCHITECTURE
# ==========================================
# Force the heavy 14B Transformer onto GPU 0 exclusively
print("Loading Quantized Transformer onto cuda:0...")
transformer = WanTransformer3DModel.from_single_file(
    GGUF_FILE_PATH,
    quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
    torch_dtype=torch.bfloat16,
    local_files_only=True,
).to("cuda:0")

# Force the VAE onto GPU 1 exclusively
print("Loading VAE onto cuda:1...")
vae = AutoencoderKLWan.from_pretrained(
    local_model_path, subfolder="vae", torch_dtype=torch.bfloat16, local_files_only=True
).to("cuda:1")

# Initialize pipeline without automatic offloading wrappers
pipe = WanImageToVideoPipeline.from_pretrained(
    local_model_path,
    transformer=transformer,
    text_encoder=None,
    vae=vae,
    torch_dtype=torch.bfloat16,
)

# Force the CLIP vision image encoder component to stay on GPU 1
if hasattr(pipe, "image_encoder") and pipe.image_encoder is not None:
    print("Moving Image Encoder to cuda:1...")
    pipe.image_encoder.to("cuda:1")

# FIX: Force internal pipeline components to target specific hardware domains
# instead of relying on the global pipe.enable_model_cpu_offload() tool.
pipe.transformer.to("cuda:0")

# VAE & Attention foot-saving features
pipe.vae.enable_tiling()
pipe.vae.enable_slicing()
pipe.enable_attention_slicing()

# Load source image
image = load_image(
    "src/services/Wan2.1/Wan2.1-I2V-14B-480P-Diffusers/examples/i2v_input.JPG"
)

print("Starting generation loop...")
torch.cuda.empty_cache()

# ==========================================
# STEP 3: RUN INFERENCE WITH STRICT GRAPHICS CONTEXTS
# ==========================================
with torch.no_grad():
    # Force PyTorch SDPA to tightly compress cross-attention layer matrices
    with torch.backends.cuda.sdp_kernel(
        enable_flash=True, enable_math=False, enable_mem_efficient=True
    ):
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
