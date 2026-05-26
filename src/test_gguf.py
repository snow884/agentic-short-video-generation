import torch
from diffusers import (
    AutoencoderKLWan,
    GGUFQuantizationConfig,
    WanImageToVideoPipeline,
    WanTransformer3DModel,
)
from diffusers.utils import export_to_video, load_image
from transformers import CLIPVisionModel

# Setup paths and device
BASE_MODEL_ID = "src/services/Wan2.1/Wan-AI/Wan2.1-I2V-14B-480P"
GGUF_FILE_PATH = (
    "src/services/Wan2.1/Wan2.1-I2V-14B-480P-gguf/wan2.1-i2v-14b-480p-Q4_K_S.gguf"
)
device = "cuda"

# Load components: VAE, Image Encoder, and quantized Transformer
image_encoder = CLIPVisionModel.from_pretrained(
    BASE_MODEL_ID, subfolder="image_encoder", torch_dtype=torch.float32
)
vae = AutoencoderKLWan.from_pretrained(
    BASE_MODEL_ID, subfolder="vae", torch_dtype=torch.float32
)
transformer = WanTransformer3DModel.from_single_file(
    GGUF_FILE_PATH,
    quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
    torch_dtype=torch.bfloat16,
)

# Initialize pipeline with necessary components
pipe = WanImageToVideoPipeline.from_pretrained(
    BASE_MODEL_ID,
    transformer=transformer,
    vae=vae,
    image_encoder=image_encoder,
    torch_dtype=torch.bfloat16,
)

pipe.to(device)
pipe.enable_model_cpu_offload()  # Reduces VRAM usage

# Generate video
image = load_image("path_to_your_image.jpg")
video = pipe(
    prompt="A cinematic shot of a white cat...",
    image=image,
    num_frames=81,
    height=480,
    width=832,
    num_inference_steps=40,
    guidance_scale=6.0,
).frames[0]

# Export result
export_to_video(video, "output.mp4", fps=16)
