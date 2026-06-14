# Agentic Tasks — AI Event Research & TikTok Video Generator

## Purpose

This repository contains tools and pipelines to research trending events on the internet, generate short videos using AI video-generation tools, and publish the resulting content to TikTok.

The primary goal is to automate the research → generation → publish workflow so creators can quickly produce timely, engaging short-form videos.

## High-level workflow

1. Discover and research events, topics, and sources on the internet.
2. Produce or synthesize assets (images, audio, captions) using AI models and local services in `src/services`.
3. Assemble and render short videos using the generation pipelines under `weekend_short_generation` and `src/services` tools.
4. Publish videos to TikTok (manual or scripted publishing depending on account/API access).

## Repo layout (important folders)

- `src/` — core scripts: research, utilities, and small tools (e.g. `research_agent.py`, `llm.py`).
- `src/services/` — AI-generation integrations (e.g. SadTalker, Wan2.1) and helpers.
- `weekend_short_generation/` — task flows and task-specific generators used to build short videos.
- `data/` — input assets and temporary outputs (audio, images, video).
- `pics/` — static images and logos.

## Requirements

- Python 3.8+ recommended.
- Install dependencies:

```bash
pip install -r requirements.txt
```

Note: Some services under `src/services` have additional system and GPU dependencies; consult their `requirements.txt` files (for example `src/services/SadTalker/req.txt`).

## Quick start

1. Install Python dependencies: see `requirements.txt`.
2. Run research agent to collect candidate topics:

```bash
python src/research_agent.py
```

3. Use the task generators under `weekend_short_generation/tasks/` to build a video from researched data. Example (replace with the task you need):

```bash
python weekend_short_generation/flow.py
```

4. Review the generated video in `data/video/` then publish to TikTok manually or via your publishing script.

### Additional prerequisites for `weekend_short_generation/flow.py`

The `weekend_short_generation/flow.py` pipeline expects several local services to be running before you execute the flow:

- **Prefect:** Start Prefect in a separate terminal so the flow orchestration is available (for example, `prefect orion start` or `prefect agent start` depending on your Prefect setup).
- **ComfyUI:** Start ComfyUI (the local image-generation UI) so the generation tasks can connect to it. Follow the ComfyUI instructions for launching the local web UI.
- **Ollama:** Install Ollama and ensure its local API/daemon is running and accessible to the flow.

Example (illustrative) commands — adjust per your local installs and docs:

```bash
# Terminal 1: start Prefect
prefect server start

# Terminal 2: start ComfyUI (follow ComfyUI's startup instructions)
# cd /path/to/ComfyUI && python launch.py

# Ensure Ollama is installed and running (see Ollama docs for exact command)
ollama status
```

## Tips & Notes

- Keep sensitive credentials (API keys, TikTok tokens) out of the repo; use environment variables or a secrets manager.
- For reproducible results, run heavy model workloads on a machine with a capable GPU and the appropriate drivers.
- Many generation modules include their own README and model download scripts — follow those when using specific services.

## Contributing

Contributions are welcome. Open issues or PRs describing desired features, bug fixes, or new generation tasks.

## License

Specify a license for your project (e.g. MIT) by adding a `LICENSE` file.
