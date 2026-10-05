# Stack Lamp | Self-Hosted AI Coding Assistant

## Introduction

Stack Lamp is a local-first AI coding assistant. Each user provides their own model API details and runs the app on their own machine. Select project files, describe a task, review the proposed changes, and apply them when ready.

This repository provides the application source code. It does not include a shared Stack Lamp-hosted service or pay for users' model requests. API usage is billed to the account associated with the API credentials supplied by the user.

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

Stack Lamp opens `http://127.0.0.1:8765`. Open Settings and provide your personal API key, API base URL, and model name. Use a provider endpoint that supports the OpenAI Responses API, including JSON object output and reasoning effort parameters.

The API settings are stored in a per-user configuration directory outside the project (`%LOCALAPPDATA%\StackLamp\settings.json` on Windows, or `~/.config/stacklamp/settings.json` on macOS and Linux). The file contains credentials in plain text; do not share it or sync it to a public location. It is not included in Git. You can configure `MODEL_API_KEY`, `MODEL_NAME`, `MODEL_BASE_URL`, and `MODEL_REASONING_EFFORT` through environment variables instead. See [`.env.example`](.env.example) for their names.

Only the text files you select are sent to the configured model provider. Do not select files containing passwords, access tokens, customer data, or other sensitive information. Model output can be incorrect; review the diff before applying it.

### Large projects and directory selection

The project file list and chat request do not impose a file-count limit. The existing web interface still selects files individually. API clients may pass a project-relative directory path in the `files` array to include all supported text files in that directory and its non-ignored subdirectories. For example, `["src", "README.md"]` includes supported files under `src/` plus the root `README.md`. Ignored dependency/build directories, symlinks, unsupported files, and files over 300 KB are excluded. Each file included in the model context must also be no larger than 120 KB, and the total context is capped at 500 KB.

The configured provider must support the OpenAI Responses API format and the parameters listed above. Check your provider's documentation for the correct API base URL and model name. Stack Lamp does not choose or bundle a model provider.

## Optional Cloud Mode

Cloud mode is for operators who deploy and maintain their own server. It requires Supabase Auth and Postgres. The database setup script is [`supabase/schema.sql`](supabase/schema.sql). Configure registration, email verification, and the production site URL in Supabase, then deploy to a Docker-compatible platform.

Cloud mode currently uses one server-side model API configuration for that deployment. Individual cloud users cannot enter their own API details yet. This mode is separate from the local personal API workflow and is not a Stack Lamp-hosted service.

| Variable | Purpose |
| --- | --- |
| `APP_MODE` | Set to `public` to enable cloud accounts |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase public anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase server key; keep it only in the hosting platform's server-side environment |
| `MODEL_API_KEY` | Personal model API key; keep server-side for cloud deployments |
| `MODEL_NAME` | Model name supplied by the provider |
| `MODEL_BASE_URL` | Provider API base URL |
| `MODEL_REASONING_EFFORT` | Reasoning effort parameter; defaults to `low` |

The Docker container listens on the platform-provided `PORT`. Enable HTTPS and add the production domain to the Supabase Auth site and redirect URL settings. Never put server-side keys in browser code or a public repository.

Cloud uploads are limited to 25 MB; extracted contents are limited to 100 MB and 5,000 files. Workspaces are removed after 24 hours without activity. New accounts are limited to 20 AI requests per month by default. This is a request-count limit, not token-based billing. Subscription payments are not implemented.

## Tech Stack

- Python, FastAPI, and Uvicorn for the local and cloud services.
- HTML, CSS, and JavaScript for the web interface.
- The OpenAI Python SDK to call a provider's compatible Responses API.
- Supabase Auth and Postgres for optional cloud login and request quotas.
- Docker for optional cloud deployment.

## Development Notes

- Local mode binds to `127.0.0.1` by default and is accessible only from the local machine.
- The service does not execute project code. Applying a change only writes to files allowed in the workspace.
- In cloud mode, selected source code is sent to the model API configured by the operator. Tell users how their data is handled before offering a deployment.
- Subscription billing, recurring payments, and payment callbacks are not implemented.
