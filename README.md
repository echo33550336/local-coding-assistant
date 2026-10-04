# Stack Lamp | DeepSeek-Powered AI Coding Assistant

Stack Lamp brings AI into your local project. Select the files relevant to your task, describe what you want to do, and review the proposed diff before applying it. By default, project files are read and updated on your machine; only the files you select are sent to the DeepSeek API.

Stack Lamp uses DeepSeek and the `deepseek-flash` model by default. Local use requires no Stack Lamp account or server deployment. You can optionally configure Supabase to enable cloud accounts. This repository contains the source code; it does not host a public online service.

## Features

- Browse project files and choose which files to include in a request.
- Ask the assistant to explain code, investigate issues, implement small changes, or improve documentation.
- Review complete file diffs before deciding whether to apply changes.
- Optionally enable cloud login and isolated temporary workspaces with Supabase.

## Run Locally

You need Python 3.10 or later and a DeepSeek API key. Dependencies are installed on the first launch.

In PowerShell, run:

```powershell
$env:DEEPSEEK_API_KEY = "your DeepSeek API key"
Set-Location "path\to\local-coding-assistant"
.\启动助手.ps1
```

Stack Lamp opens `http://127.0.0.1:8765`. The default model is `deepseek-flash`, and the API base URL is `https://api.deepseek.com`. You can set `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`, or `DEEPSEEK_REASONING_EFFORT` before launch. See [`.env.example`](.env.example) for the available variables. Never commit a real API key to GitHub.

Only the text files you select are sent to the configured model provider. Do not select files containing passwords, access tokens, customer data, or other sensitive information. Model output can be incorrect; review the diff before applying it.

The DeepSeek API supports the OpenAI Responses API format. See the [official DeepSeek API documentation](https://api-docs.deepseek.com/) for current endpoints, model names, and parameters.

## Optional Cloud Deployment

Cloud mode requires Supabase Auth and Postgres. The database setup script is [`supabase/schema.sql`](supabase/schema.sql). Configure registration, email verification, and the production site URL in Supabase, then deploy the project to a Docker-compatible platform with these server-side environment variables:

| Variable | Purpose |
| --- | --- |
| `APP_MODE` | Set to `public` to enable cloud accounts |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase public anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase server key; keep it only in the hosting platform's server-side environment |
| `DEEPSEEK_API_KEY` | Server-side DeepSeek API key |
| `DEEPSEEK_MODEL` | Model name; defaults to `deepseek-flash` |
| `DEEPSEEK_BASE_URL` | API base URL; defaults to `https://api.deepseek.com` |
| `DEEPSEEK_REASONING_EFFORT` | Reasoning effort; defaults to `low` |

The Docker container listens on the platform-provided `PORT`. Enable HTTPS and add the production domain to the Supabase Auth site and redirect URL settings. Never put model keys or the Supabase service role key in browser code, client-side settings, or a public repository.

In cloud mode, users upload projects as ZIP files. Each account gets a separate temporary workspace. ZIP uploads are limited to 25 MB; extracted contents are limited to 100 MB and 5,000 files. Workspaces are removed after 24 hours without activity. New accounts are limited to 20 AI requests per month by default. This is a request-count limit, not token-based billing. Subscription payments are not implemented yet.

## Tech Stack

- Python, FastAPI, and Uvicorn for the local and cloud services.
- HTML, CSS, and JavaScript for the web interface.
- The OpenAI Python SDK to call DeepSeek's compatible Responses API.
- Supabase Auth and Postgres for optional cloud login and request quotas.
- Docker for optional cloud deployment.

## Development Notes

- Local mode binds to `127.0.0.1` by default and is accessible only from the local machine.
- The service does not execute project code. Applying a change only writes to files allowed in the workspace.
- In cloud mode, selected source code is sent to the DeepSeek API account configured by the deployment. Before launch, explain how user data is processed and provide any required privacy information and terms of service.
- Subscription billing, recurring payments, and payment callbacks are not implemented.
