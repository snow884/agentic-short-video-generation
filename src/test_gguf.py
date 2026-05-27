import torch
from diffusers import (
    AutoencoderKLWan,
    GGUFQuantizationConfig,
    WanImageToVideoPipeline,
    WanTransformer3DModel,
)
from diffusers.utils import export_to_video, load_image
from transformers import CLIPVisionModel

# Setup paths
local_model_path = "./src/services/Wan2.1/Wan2.1-I2V-14B-480P-Diffusers/"
GGUF_FILE_PATH = (
    "./src/services/Wan2.1/Wan2.1-I2V-14B-480P-gguf/wan2.1-i2v-14b-480p-Q4_K_S.gguf"
)

# 1. Load Image Encoder explicitly onto GPU 1 to save space on GPU 0
print("Loading Image Encoder onto cuda:1...")
image_encoder = CLIPVisionModel.from_pretrained(
    local_model_path,
    subfolder="image_encoder",
    torch_dtype=torch.bfloat16,
    local_files_only=True,
).to("cuda:1")
image_encoder.gradient_checkpointing_enable()

# 2. VAE requires high precision (float32). Load onto GPU 1 where it won't fight with the transformer
print("Loading VAE onto cuda:1...")
vae = AutoencoderKLWan.from_pretrained(
    local_model_path, subfolder="vae", torch_dtype=torch.float32, local_files_only=True
).to("cuda:1")

# 3. Load the heavy 14B GGUF Transformer onto GPU 0
print("Loading Quantized Transformer onto cuda:0...")
transformer = WanTransformer3DModel.from_single_file(
    GGUF_FILE_PATH,
    quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
    torch_dtype=torch.bfloat16,
    local_files_only=True,
).to("cuda:0")

# 4. Initialize pipeline
pipe = WanImageToVideoPipeline.from_pretrained(
    local_model_path,
    transformer=transformer,
    vae=vae,
    image_encoder=image_encoder,
    torch_dtype=torch.bfloat16,
)

# CRITICAL: Do NOT use pipe.to("cuda") or enable_model_cpu_offload().
# Instead, we balance the components manually or use device_map if available.
# To ensure the text encoders also use GPU 1, map them explicitly:
if hasattr(pipe, "text_encoder"):
    pipe.text_encoder.to("cuda:1")
if hasattr(pipe, "text_encoder_2"):
    pipe.text_encoder_2.to("cuda:1")

# 5. Enable memory optimizations for the layers inside the models
pipe.enable_attention_slicing()
pipe.vae.enable_tiling()  # Prevents OOM during the final video decoding phase
pipe.vae.enable_slicing()

# Generate video
image = load_image(
    "src/services/Wan2.1/Wan2.1-I2V-14B-480P-Diffusers/examples/i2v_input.JPG"
)

print("Starting generation loop...")
# Use PyTorch SDPA context for memory efficiency
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
