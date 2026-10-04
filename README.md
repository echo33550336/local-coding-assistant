# Stack Lamp | Self-Hosted AI Coding Assistant

## Introduction

Stack Lamp is a local-first AI coding assistant powered by DeepSeek. Each user brings their own API key and runs the app on their own machine. Select project files, describe a task, review the proposed diff, and apply changes when ready.

This repository provides the application source code. It does not include a shared Stack Lamp-hosted service or pay for users' model requests. DeepSeek API usage is billed to the account associated with each user's key.

## Features

- Browse a local project and choose which files to include in a request.
- Ask the assistant to explain code, investigate issues, implement small changes, or improve documentation.
- Review complete file diffs before applying changes.
- Keep project files and API key configuration on the user's own machine.
- Optionally self-host a cloud deployment with Supabase; see the cloud-mode limitations below.

## Run Locally

You need Python 3.10 or later. On first launch, the included launcher installs the project dependencies.

In PowerShell, run:

```powershell
Set-Location "path\to\local-coding-assistant"
.\start.ps1
```

Stack Lamp opens `http://127.0.0.1:8765`. Click the gear icon, enter your own DeepSeek API key, and save it. The default model is `deepseek-flash`, using `https://api.deepseek.com`.

The key is stored in a per-user configuration directory outside the project (`%LOCALAPPDATA%\StackLamp\settings.json` on Windows, or `~/.config/stacklamp/settings.json` on macOS and Linux). It is a plain-text local file; do not share it or sync it to a public location. It is not included in Git. If no key is saved in Settings, the app can use `DEEPSEEK_API_KEY` from the environment instead. A key saved through Settings takes precedence. You can also configure `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_REASONING_EFFORT` through environment variables. See [`.env.example`](.env.example) for their names.

Only the text files you select are sent to the configured model provider. Do not select files containing passwords, access tokens, customer data, or other sensitive information. Model output can be incorrect; review the diff before applying it.

The DeepSeek API supports the OpenAI Responses API format. See the [official DeepSeek API documentation](https://api-docs.deepseek.com/) for current endpoints, model names, and parameters.

## Optional Cloud Mode

Cloud mode is for operators who deploy and maintain their own server. It requires Supabase Auth and Postgres. The database setup script is [`supabase/schema.sql`](supabase/schema.sql). Configure registration, email verification, and the production site URL in Supabase, then deploy to a Docker-compatible platform.

Cloud mode currently uses one server-side `DEEPSEEK_API_KEY` for that deployment. Individual cloud users cannot enter their own API keys yet. This mode is separate from the local bring-your-own-key workflow and is not a Stack Lamp-hosted service.

| Variable | Purpose |
| --- | --- |
| `APP_MODE` | Set to `public` to enable cloud accounts |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase public anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase server key; keep it only in the hosting platform's server-side environment |
| `DEEPSEEK_API_KEY` | Server-side DeepSeek API key used by the deployment |
| `DEEPSEEK_MODEL` | Model name; defaults to `deepseek-flash` |
| `DEEPSEEK_BASE_URL` | API base URL; defaults to `https://api.deepseek.com` |
| `DEEPSEEK_REASONING_EFFORT` | Reasoning effort; defaults to `low` |

The Docker container listens on the platform-provided `PORT`. Enable HTTPS and add the production domain to the Supabase Auth site and redirect URL settings. Never put server-side keys in browser code or a public repository.

Cloud uploads are limited to 25 MB; extracted contents are limited to 100 MB and 5,000 files. Workspaces are removed after 24 hours without activity. New accounts are limited to 20 AI requests per month by default. This is a request-count limit, not token-based billing. Subscription payments are not implemented.

## Tech Stack

- Python, FastAPI, and Uvicorn for the local and cloud services.
- HTML, CSS, and JavaScript for the web interface.
- The OpenAI Python SDK to call DeepSeek's compatible Responses API.
- Supabase Auth and Postgres for optional cloud login and request quotas.
- Docker for optional cloud deployment.

## Development Notes

- Local mode binds to `127.0.0.1` by default and is accessible only from the local machine.
- The service does not execute project code. Applying a change only writes to files allowed in the workspace.
- In cloud mode, selected source code is sent to the DeepSeek API account configured by the operator. Tell users how their data is handled before offering a deployment.
- Subscription billing, recurring payments, and payment callbacks are not implemented.
