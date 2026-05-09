---
description: Run scripts/dev.sh to control local dev stack (backend + celery + frontend + docker)
argument-hint: "[start|stop|stop --all|restart|status|logs [backend|celery|frontend]]"
allowed-tools: Bash(./scripts/dev.sh:*)
---

<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->


Run `./scripts/dev.sh $ARGUMENTS` from repo root via the Bash tool.

If `$ARGUMENTS` is empty, run `./scripts/dev.sh --help` to show usage.

For `logs` without a name, it tails all logs and blocks — run it with `run_in_background: true` so the user can keep going. For other subcommands run foreground and report exit status + relevant output (URLs for `start`, pids for `status`).

After `start`, remind the user:
- Backend: http://localhost:8000 (docs: /docs)
- Frontend: http://localhost:3000
- `/dev logs` to tail, `/dev stop` to stop.
