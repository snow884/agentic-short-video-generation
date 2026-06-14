# Privacy Policy

Last updated: 2026-06-14

This Privacy Policy describes how the Agentic Tasks project ("we", "us", or "the project") handles information collected or processed as part of running the code and using the associated tooling and services. This policy describes only the project itself — separate third-party services (APIs, cloud providers, or model hosts) have their own policies which you should review.

1. Data we may access or create

- Local configuration and credentials: the repository may use a local `.env` file or environment variables to store API keys and tokens needed to access third-party services. The project itself does not transmit these files anywhere by default.
- Generated assets: images, audio, and video files created by the pipeline are stored locally under `data/` unless you configure an external storage provider.
- Logs and metadata: runtime logs, task metadata, and temporary files may be written to disk for debugging and orchestration.

2. What we do with data

- Research and generation: the pipeline processes content (text, images, audio) to create derivative video clips.
- Optional uploads: the project can publish videos to a configured TikTok account (you must provide credentials/token for publishing). Publishing is an explicit action and not performed automatically without configuration.

3. Third-party services

- When you configure API providers (e.g. search APIs, model hosts, Ollama, ComfyUI), those providers may collect, store, or process data according to their policies. You should read and understand their privacy terms before using them with this project.

4. Secrets and credentials

- Do not commit secrets to git. Use environment variables or a secrets manager. This project recommends storing credentials locally in a `.env` file that is ignored by git.

5. Data retention and deletion

- Generated files and logs are stored locally. To remove them, delete the relevant files/folders (for example, `data/`). If you have pushed any sensitive files to a remote git repository, rotate the exposed credentials immediately and purge the repository history.

6. Contact

If you have privacy questions or concerns about this project, open an issue in the repository or contact the repository owner.
