---
description: Run scripts/dev.sh to control local dev stack (postgres + redis + meilisearch + backend + celery + frontend + log viewer + ngrok)
argument-hint: "[start [--tunnel] | stop [--all] | restart | reset [--tunnel] [--yes] | status | logs [backend|celery|frontend|ngrok|log_viewer] | tunnel | tunnel-url]"
allowed-tools: Bash(./scripts/dev.sh:*)
---

<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->

Run `./scripts/dev.sh $ARGUMENTS` from repo root via the Bash tool.

The script drives one of two interchangeable infrastructure backends and picks automatically: **docker** (docker compose) or **native** (no Docker, no root — `scripts/native_infra.sh`, installed under `~/.local/share/khanabazaar`). A provisioned native env wins over a merely-installed Docker; `KB_INFRA_MODE=docker|native` forces one. Ports, credentials and `.env` are identical either way, so every subcommand below behaves the same. `./scripts/dev.sh --help` prints the active backend.

If `$ARGUMENTS` is empty, run `./scripts/dev.sh --help` to show usage.

## Subcommand handling

- **`logs [name]`** uses `exec tail -f` and blocks. Always run with `run_in_background: true` so the user can keep working. Valid targets: `backend`, `celery`, `frontend`, `ngrok`, `log_viewer`. No name tails `backend + celery + frontend` together (ngrok/log_viewer excluded).
- **All other subcommands** run foreground. Report exit status + relevant output.

## What to surface per subcommand

- **`start`** / **`restart`** — relay all URLs from the script's tail output:
  - Backend: `http://localhost:8000` (docs: `/docs`)
  - Frontend: `http://localhost:3000`
  - Meilisearch: `http://localhost:7700`
  - Log viewer: `http://localhost:8001` (or `$LOG_VIEWER_PORT` if overridden)
  - Logs dir: `.dev/logs/`
- **`start --tunnel`** — same as `start`, plus the ngrok public URL and `<url>/dev-logs/` (log viewer proxied through frontend rewrite). Useful for mobile testing.
- **`stop`** — stops ngrok, log viewer, frontend, celery, backend. Leaves the infra services (postgres + redis + meilisearch) running.
- **`stop --all`** — also stops postgres + redis + meilisearch. Nothing is left running: unlike the Docker backend (`restart: always`), the native services have no auto-restart, so they stay down across reboots until the next `start`.
- **`reset`** — HARD RESET. Destructive. Stops every app process, wipes all Postgres / Redis / Meilisearch state, rebuilds it empty, applies alembic migrations, reseeds the dev DB via `scripts/seed_database.py`, then starts everything back up. On the Docker backend that means `docker compose down -v` + `pull` + recreate; on the native backend it deletes the data dirs under `~/.local/share/khanabazaar/data` and re-runs `initdb`. **Interactive prompt requires typing `reset` to confirm** — pass `--yes` (or `-y`) to skip. Pass `--tunnel` to also start ngrok at the end. Warn the user before invoking that all local DB / Redis / Meili data will be lost; if running non-interactively (no terminal for the prompt), pass `--yes` only after explicit user approval.
- **`status`** — relay pid table, the infra status block (`docker compose ps`, or the native per-service probe list), and the ngrok tunnel list verbatim. Includes inspector URL `http://localhost:4040` when ngrok is up.
- **`tunnel`** — starts ngrok (and log viewer if needed). Surface the resolved public URL.
- **`tunnel-url`** — prints current public URL on stdout. Non-zero exit means no tunnel running.

## Post-`start` reminder

After a successful `start`, remind the user:
- `/dev logs [name]` to tail one stream (run in background)
- `/dev status` to check pids + tunnels
- `/dev stop` to stop app processes
- `/dev stop --all` to also stop postgres + redis + meilisearch
- `/dev reset` for a destructive hard reset (wipes data, reseeds DB) — only when the user asks
- `/dev tunnel-url` to reprint the current tunnel URL (when started with `--tunnel`)
