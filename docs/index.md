# Agentic Tasks — AI Event Research & TikTok Video Generator

## Project Overview

Agentic Tasks is an automation toolkit for researching trending events on the internet, generating short AI videos from the gathered material, and publishing the resulting clips to TikTok. The pipeline is designed to accelerate the workflow: discover → generate → produce → publish.

## Purpose

- Research current events and topics using `src/research_agent.py` and related tools.
- Generate and assemble short-form video assets using the generation tasks under `weekend_short_generation/` and `src/services/`.
- Publish completed videos to a dedicated TikTok channel for distribution and audience testing.

## Where the videos are published

- 🎬 TikTok channel: https://www.tiktok.com/@americanaireacts0

## Site pages

- [Privacy Policy](./privacy.md) — explains data handling for this project.
- [Terms of Service](./terms.md) — usage terms and disclaimers.

## Notes

- This repo contains integrations that may require local services (Prefect, ComfyUI, Ollama) and GPU resources. See `README.md` for details and startup instructions.
- This site is a static site deployed via the repository's GitHub Actions workflow; content here is informational and not a substitute for legal advice.
