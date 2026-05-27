import gc
import os

import torch
from diffusers import (
    AutoencoderKLWan,
    GGUFQuantizationConfig,
    WanImageToVideoPipeline,
    WanTransformer3DModel,
)
from diffusers.utils import export_to_video, load_image
from transformers import (
    AutoTokenizer,
    CLIPImageProcessor,
    CLIPVisionModel,
    T5EncoderModel,
)

# 1. Device and allocator setup
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

local_model_path = "./src/services/Wan2.1/Wan2.1-I2V-14B-480P-Diffusers/"
GGUF_FILE_PATH = (
    "./src/services/Wan2.1/Wan2.1-I2V-14B-480P-gguf/wan2.1-i2v-14b-480p-Q4_K_S.gguf"
)
prompt = "A cinematic shot of a white cat."

# Load source image
image = load_image(
    "src/services/Wan2.1/Wan2.1-I2V-14B-480P-Diffusers/examples/i2v_input.JPG"
)

# ===================================================
# STEP 1: EXTRACT TEXT EMBEDDINGS ON CPU
# ===================================================
print("Encoding text prompts on CPU...")
tokenizer = AutoTokenizer.from_pretrained(local_model_path, subfolder="tokenizer")
text_encoder = T5EncoderModel.from_pretrained(
    local_model_path,
    subfolder="text_encoder",
    torch_dtype=torch.bfloat16,
    device_map={"": "cpu"},
    local_files_only=True,
)

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

del text_encoder, tokenizer
gc.collect()

# ===================================================
# STEP 2: EXTRACT IMAGE FEATURES ON GPU 1
# ===================================================
print("Extracting image features on cuda:1...")
image_processor = CLIPImageProcessor.from_pretrained(
    local_model_path, subfolder="image_processor"
)
image_encoder = CLIPVisionModel.from_pretrained(
    local_model_path,
    subfolder="image_encoder",
    torch_dtype=torch.bfloat16,
    local_files_only=True,
).to("cuda:1")

with torch.no_grad():
    clip_image = image_processor(images=image, return_tensors="pt").pixel_values.to(
        "cuda:1", dtype=torch.bfloat16
    )
    image_embeds = image_encoder(clip_image).last_hidden_state
    # Keep embeddings mapped to cuda:0 so they match the transformer's domain
    image_embeds = image_embeds.to("cuda:0")

del image_encoder, image_processor
torch.cuda.empty_cache()
gc.collect()

# ===================================================
# STEP 3: LAUNCH GPU PIPELINE
# ===================================================
print("Loading Quantized Transformer onto cuda:0...")
transformer = WanTransformer3DModel.from_single_file(
    GGUF_FILE_PATH,
    quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
    torch_dtype=torch.bfloat16,
    local_files_only=True,
).to("cuda:0")

print("Loading VAE onto cuda:1...")
vae = AutoencoderKLWan.from_pretrained(
    local_model_path, subfolder="vae", torch_dtype=torch.bfloat16, local_files_only=True
).to("cuda:1")

# FIX: Create a mock class inheriting from torch.nn.Module
# This satisfies the internal type checks inside Diffusers pipeline loaders.
class MockImageEncoder(torch.nn.Module):
    def __init__(self):
        super().__init__()
        # Create a dummy config class so that `image_encoder.config` doesn't throw an AttributeError
        class DummyConfig:
            pass

        self.config = DummyConfig()


pipe = WanImageToVideoPipeline.from_pretrained(
    local_model_path,
    transformer=transformer,
    text_encoder=None,
    image_encoder=MockImageEncoder(),  # Passes the type validation check
    vae=vae,
    torch_dtype=torch.bfloat16,
)

# VAE & Attention optimization configs
pipe.vae.enable_tiling()
pipe.vae.enable_slicing()
pipe.enable_attention_slicing()

print("Starting generation loop...")
torch.cuda.empty_cache()

# ===================================================
# STEP 4: RUN INFERENCE WITH CORRECT INPUTS
# ===================================================
with torch.no_grad():
    with torch.nn.attention.sdpa_kernel(
        [
            torch.nn.attention.SDPBackend.FLASH_ATTENTION,
            torch.nn.attention.SDPBackend.EFFICIENT_ATTENTION,
        ]
    ):
        video = pipe(
            prompt_embeds=prompt_embeds,
            negative_prompt_embeds=negative_prompt_embeds,
            image=image,  # FIX: Re-enable raw image so the VAE can process initial latents
            image_embeds=image_embeds,  # Pass our pre-computed features
            num_frames=81,
            height=480,
            width=832,
            num_inference_steps=40,
            guidance_scale=6.0,
        ).frames[0]

# Export result
export_to_video(video, "output.mp4", fps=16)
print("Video saved successfully!")
