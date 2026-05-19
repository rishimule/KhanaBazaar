---
description: Run scripts/dev.sh to control local dev stack (postgres + redis + backend + celery + frontend + log viewer + ngrok)
argument-hint: "[start [--tunnel] | stop [--all] | restart | status | logs [backend|celery|frontend|ngrok|log_viewer] | tunnel | tunnel-url]"
allowed-tools: Bash(./scripts/dev.sh:*)
---

<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->

Run `./scripts/dev.sh $ARGUMENTS` from repo root via the Bash tool.

If `$ARGUMENTS` is empty, run `./scripts/dev.sh --help` to show usage.

## Subcommand handling

- **`logs [name]`** uses `exec tail -f` and blocks. Always run with `run_in_background: true` so the user can keep working. Valid targets: `backend`, `celery`, `frontend`, `ngrok`, `log_viewer`. No name tails `backend + celery + frontend` together (ngrok/log_viewer excluded).
- **All other subcommands** run foreground. Report exit status + relevant output.

## What to surface per subcommand

- **`start`** / **`restart`** — relay all URLs from the script's tail output:
  - Backend: `http://localhost:8000` (docs: `/docs`)
  - Frontend: `http://localhost:3000`
  - Log viewer: `http://localhost:8001` (or `$LOG_VIEWER_PORT` if overridden)
  - Logs dir: `.dev/logs/`
- **`start --tunnel`** — same as `start`, plus the ngrok public URL and `<url>/dev-logs/` (log viewer proxied through frontend rewrite). Useful for mobile testing.
- **`stop`** — stops ngrok, log viewer, frontend, celery, backend. Leaves docker (postgres + redis) running.
- **`stop --all`** — also stops docker postgres + redis.
- **`status`** — relay pid table, docker compose ps, and the ngrok tunnel list verbatim. Includes inspector URL `http://localhost:4040` when ngrok is up.
- **`tunnel`** — starts ngrok (and log viewer if needed). Surface the resolved public URL.
- **`tunnel-url`** — prints current public URL on stdout. Non-zero exit means no tunnel running.

## Post-`start` reminder

After a successful `start`, remind the user:
- `/dev logs [name]` to tail one stream (run in background)
- `/dev status` to check pids + tunnels
- `/dev stop` to stop app processes
- `/dev stop --all` to also stop postgres + redis
- `/dev tunnel-url` to reprint the current tunnel URL (when started with `--tunnel`)
