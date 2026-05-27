import os

import av
import numpy as np
import torch
from diffusers import WanImageToVideoPipeline, WanTransformer3DModel
from diffusers.quantization_config import GGUFQuantizationConfig
from PIL import Image

# 1. Configuration & Local Paths
# Set this to the absolute or relative path where your .gguf file is stored
LOCAL_GGUF_PATH = (
    "./src/services/Wan2.1/Wan2.1-I2V-14B-480P-gguf/wan2.1-i2v-14b-480p-Q4_K_S.gguf"
)

if not os.path.exists(LOCAL_GGUF_PATH):
    raise FileNotFoundError(f"Could not find the local GGUF file at: {LOCAL_GGUF_PATH}")

# Define VRAM allocations to split the model across both RTX 5070s
max_memory = {0: "14GB", 1: "14GB"}

# 2. Load the Transformer locally from the GGUF file
print(f"Loading quantized transformer from local file: {LOCAL_GGUF_PATH}...")
transformer = WanTransformer3DModel.from_single_file(
    LOCAL_GGUF_PATH,
    quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
    torch_dtype=torch.bfloat16,
    device_map="auto",
    max_memory=max_memory,
)

# 3. Assemble the Pipeline
print("Assembling WanImageToVideoPipeline...")
# The pipeline structure configuration is fetched from the base hub layout,
# but we override the transformer with our locally loaded GGUF instance.
pipe = WanImageToVideoPipeline.from_pretrained(
    "./src/services/Wan2.1/Wan2.1-I2V-14B-480P-Diffusers/",
    transformer=transformer,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    max_memory=max_memory,
)

# Performance tweaks for dual-GPU VRAM overhead
pipe.vae.enable_tiling()
pipe.vae.enable_slicing()

# 4. Input Processing
input_image_path = "input_scene.jpg"
if not os.path.exists(input_image_path):
    print("Creating placeholder image...")
    img = Image.new("RGB", (832, 480), color=(40, 40, 40))
    img.save(input_image_path)

init_image = Image.open(input_image_path).convert("RGB").resize((832, 480))
prompt = "Cinematic slow motion camera pan, hyperrealistic details, 4k resolution"
negative_prompt = "blurry, low quality, distorted"

# 5. Execution Loop
print("Running model inference across both RTX 5070 GPUs...")
with torch.inference_mode():
    video_frames = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=init_image,
        num_frames=81,  # Wan2.1 native frame length
        height=480,
        width=832,
        num_inference_steps=40,
        guidance_scale=6.0,
    ).frames[0]

# 6. Save Video File via PyAV
output_video_path = "local_model_output.mp4"
print(f"Encoding frames into {output_video_path}...")

container = av.open(output_video_path, mode="w")
stream = container.add_stream("libx264", rate=16)
stream.width = 832
stream.height = 480
stream.pix_fmt = "yuv420p"

for frame in video_frames:
    if isinstance(frame, torch.Tensor):
        frame = frame.cpu().numpy()
    if isinstance(frame, np.ndarray):
        img_frame = Image.fromarray((frame * 255).astype(np.uint8))
    else:
        img_frame = frame

    av_frame = av.VideoFrame.from_image(img_frame)
    for packet in stream.encode(av_frame):
        container.mux(packet)

for packet in stream.encode():
    container.mux(packet)
container.close()

print("Process finished successfully!")
