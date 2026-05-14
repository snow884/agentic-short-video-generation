import argparse
import gc
from typing import Any, Dict

from fastapi import Body, FastAPI, HTTPException

app = FastAPI()


@app.post("/inference/")
def inference(args: Dict[str, Any] = Body(...)):
    import torch
    from generate import generate, str2bool

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--task",
        type=str,
        default="t2v-14B",
        # choices=list(WAN_CONFIGS.keys()),
        help="The task to run.",
    )
    parser.add_argument(
        "--size",
        type=str,
        default="1280*720",
        # choices=list(SIZE_CONFIGS.keys()),
        help=(
            "The area (width*height) of the generated video. For the I2V task, the"
            " aspect ratio of the output video will follow that of the input image."
        ),
    )
    parser.add_argument(
        "--frame_num",
        type=int,
        default=None,
        help=(
            "How many frames to sample from a image or video. The number should be 4n+1"
        ),
    )
    parser.add_argument(
        "--ckpt_dir",
        type=str,
        default=None,
        help="The path to the checkpoint directory.",
    )
    parser.add_argument(
        "--offload_model",
        type=str2bool,
        default=None,
        help=(
            "Whether to offload the model to CPU after each model forward, reducing GPU"
            " memory usage."
        ),
    )
    parser.add_argument(
        "--ulysses_size",
        type=int,
        default=1,
        help="The size of the ulysses parallelism in DiT.",
    )
    parser.add_argument(
        "--ring_size",
        type=int,
        default=1,
        help="The size of the ring attention parallelism in DiT.",
    )
    parser.add_argument(
        "--t5_fsdp",
        action="store_true",
        default=False,
        help="Whether to use FSDP for T5.",
    )
    parser.add_argument(
        "--t5_cpu",
        action="store_true",
        default=False,
        help="Whether to place T5 model on CPU.",
    )
    parser.add_argument(
        "--dit_fsdp",
        action="store_true",
        default=False,
        help="Whether to use FSDP for DiT.",
    )
    parser.add_argument(
        "--save_file",
        type=str,
        default=None,
        help="The file to save the generated image or video to.",
    )
    parser.add_argument(
        "--src_video",
        type=str,
        default=None,
        help="The file of the source video. Default None.",
    )
    parser.add_argument(
        "--src_mask",
        type=str,
        default=None,
        help="The file of the source mask. Default None.",
    )
    parser.add_argument(
        "--src_ref_images",
        type=str,
        default=None,
        help=(
            "The file list of the source reference images. Separated by ','. Default"
            " None."
        ),
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="The prompt to generate the image or video from.",
    )
    parser.add_argument(
        "--use_prompt_extend",
        action="store_true",
        default=False,
        help="Whether to use prompt extend.",
    )
    parser.add_argument(
        "--prompt_extend_method",
        type=str,
        default="local_qwen",
        choices=["dashscope", "local_qwen"],
        help="The prompt extend method to use.",
    )
    parser.add_argument(
        "--prompt_extend_model",
        type=str,
        default=None,
        help="The prompt extend model to use.",
    )
    parser.add_argument(
        "--prompt_extend_target_lang",
        type=str,
        default="zh",
        choices=["zh", "en"],
        help="The target language of prompt extend.",
    )
    parser.add_argument(
        "--base_seed",
        type=int,
        default=-1,
        help="The seed to use for generating the image or video.",
    )
    parser.add_argument(
        "--image",
        type=str,
        default=None,
        help="[image to video] The image to generate the video from.",
    )
    parser.add_argument(
        "--first_frame",
        type=str,
        default=None,
        help=(
            "[first-last frame to video] The image (first frame) to generate the video"
            " from."
        ),
    )
    parser.add_argument(
        "--last_frame",
        type=str,
        default=None,
        help=(
            "[first-last frame to video] The image (last frame) to generate the video"
            " from."
        ),
    )
    parser.add_argument(
        "--sample_solver",
        type=str,
        default="unipc",
        choices=["unipc", "dpm++"],
        help="The solver used to sample.",
    )
    parser.add_argument(
        "--sample_steps", type=int, default=None, help="The sampling steps."
    )
    parser.add_argument(
        "--sample_shift",
        type=float,
        default=None,
        help="Sampling shift factor for flow matching schedulers.",
    )
    parser.add_argument(
        "--sample_guide_scale",
        type=float,
        default=5.0,
        help="Classifier free guidance scale.",
    )

    parser.set_defaults(**args)

    # Passing an empty list to parse_args() prevents it from reading sys.argv
    fake_args = parser.parse_args([])

    try:
        generate(fake_args)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail="Wan2.1 inference failed: " + str(e)
        )

    # 1. Delete large objects (models, tensors, optimizers)
    # del model
    # del optimizer

    # 2. Trigger Python's garbage collector
    gc.collect()

    # 3. Clear the PyTorch CUDA cache
    torch.cuda.empty_cache()

    # Optional: Release inter-process communication handles
    torch.cuda.ipc_collect()

    return "success"
