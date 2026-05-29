import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WAN_ROOT = REPO_ROOT / "src" / "services" / "Wan2.1"
DEFAULT_MODEL_REPO = "Wan-AI/Wan2.1-I2V-14B-480P"
DEFAULT_CKPT_DIR = WAN_ROOT / "Wan2.1-I2V-14B-480P"
DEFAULT_INPUT_IMAGE = WAN_ROOT / "examples" / "i2v_input.JPG"
DEFAULT_OUTPUT_FILE = REPO_ROOT / "i2v_2gpu_smoke.mp4"


def resolve_existing_path(env_var_name: str, default_path: Path) -> Path:
    candidate = Path(os.environ.get(env_var_name, default_path)).expanduser()
    if not candidate.exists():
        raise FileNotFoundError(
            f"Missing path: {candidate}. Set {env_var_name} to override it."
        )
    return candidate


def ensure_checkpoint_dir() -> Path:
    candidate = Path(os.environ.get("WAN_CKPT_DIR", DEFAULT_CKPT_DIR)).expanduser()
    if candidate.exists() and (candidate / "config.json").exists():
        return candidate

    if os.environ.get("WAN_AUTO_DOWNLOAD", "1") != "1":
        raise FileNotFoundError(
            f"Checkpoint directory not found: {candidate}. Set WAN_CKPT_DIR or enable"
            " WAN_AUTO_DOWNLOAD."
        )

    from huggingface_hub import snapshot_download

    print(f"Downloading {DEFAULT_MODEL_REPO} to {candidate}...")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=DEFAULT_MODEL_REPO,
        local_dir=str(candidate),
        local_dir_use_symlinks=False,
    )
    return candidate


def build_command(ckpt_dir: Path, output_file: Path) -> list[str]:
    nproc = int(os.environ.get("WAN_NPROC_PER_NODE", "2"))
    prompt = os.environ.get(
        "WAN_PROMPT",
        "A cinematic shot of a white cat wearing sunglasses on a surfboard, realistic"
        " beach lighting, smooth camera motion.",
    )
    size = os.environ.get("WAN_SIZE", "832*480")
    frame_num = os.environ.get("WAN_FRAME_NUM", "17")
    sample_steps = os.environ.get("WAN_SAMPLE_STEPS", "8")
    sample_shift = os.environ.get("WAN_SAMPLE_SHIFT", "3.0")
    sample_guide_scale = os.environ.get("WAN_SAMPLE_GUIDE_SCALE", "5.0")
    sample_solver = os.environ.get("WAN_SAMPLE_SOLVER", "unipc")
    input_image = resolve_existing_path("WAN_INPUT_IMAGE", DEFAULT_INPUT_IMAGE)

    command = [
        sys.executable,
        "-m",
        "torch.distributed.run",
        f"--nproc_per_node={nproc}",
        "generate.py",
        "--task",
        "i2v-14B",
        "--size",
        size,
        "--frame_num",
        frame_num,
        "--ckpt_dir",
        str(ckpt_dir),
        "--image",
        str(input_image),
        "--dit_fsdp",
        "--t5_fsdp",
        "--ulysses_size",
        str(nproc),
        "--t5_cpu",
        "--prompt",
        prompt,
        "--sample_solver",
        sample_solver,
        "--sample_steps",
        sample_steps,
        "--sample_shift",
        sample_shift,
        "--sample_guide_scale",
        sample_guide_scale,
        "--offload_model",
        "False",
        "--save_file",
        str(output_file),
    ]

    return command


def main() -> int:
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    os.chdir(WAN_ROOT)

    ckpt_dir = ensure_checkpoint_dir()
    output_file = Path(
        os.environ.get("WAN_OUTPUT_FILE", DEFAULT_OUTPUT_FILE)
    ).expanduser()
    input_image = resolve_existing_path("WAN_INPUT_IMAGE", DEFAULT_INPUT_IMAGE)

    print(f"Repo root: {REPO_ROOT}")
    print(f"Wan root: {WAN_ROOT}")
    print(f"Checkpoint dir: {ckpt_dir}")
    print(f"Input image: {input_image}")
    print(f"Output file: {output_file}")
    print(
        f"Using {os.environ.get('WAN_NPROC_PER_NODE', '2')} GPUs via"
        " torch.distributed.run"
    )

    command = build_command(ckpt_dir, output_file)
    print("Launching native Wan I2V generation...")
    completed = subprocess.run(command)
    print(f"Native generation exit code: {completed.returncode}")

    if output_file.exists():
        print(f"Generated video: {output_file} ({output_file.stat().st_size} bytes)")
    else:
        print(f"Output video not found: {output_file}")

    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
