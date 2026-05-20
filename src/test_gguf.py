import torch
from diffusers import GGUFQuantizationConfig, WanPipeline
from diffusers.utils import export_to_video, load_image

# 1. Load the GGUF model and configuration
model_id = "city96/Wan2.1-I2V-14B-480P-gguf"  # Community GGUF repo
ckpt_name = (  # Specific quant file
    "src/services/Wan2.1/Wan2.1-T2V-14B-gguf/wan2.1-i2v-480p-Q4_K_M.gguf"
)

# Use GGUFQuantizationConfig for memory-efficient loading
quant_config = GGUFQuantizationConfig(compute_dtype=torch.bfloat16)

pipe = WanPipeline.from_pretrained(
    "src/services/Wan2.1/Wan2.1-T2V-14B-gguf",  # Base config from official repo
    transformer_gguf_path=ckpt_name,  # Local or downloaded GGUF path
    gguf_config=quant_config,
    torch_dtype=torch.bfloat16,
)
pipe.to("cuda")

# 2. Prepare inputs
prompt = "A cinematic shot of a sunset over a digital ocean, high quality, 4k"
negative_prompt = "blurry, low quality, distorted"
input_image = load_image("https://example.com")  # Replace with your image

# 3. Generate the video
# Note: num_frames=81 is typical for a 5-second video at 16 fps
video_frames = pipe(
    prompt=prompt,
    negative_prompt=negative_prompt,
    image=input_image,
    num_frames=81,
    height=480,
    width=832,  # Standard 16:9 for 480p
    guidance_scale=5.0,
    num_inference_steps=50,
).frames[0]

# 4. Save result
export_to_video(video_frames, "output_video.mp4", fps=16)
