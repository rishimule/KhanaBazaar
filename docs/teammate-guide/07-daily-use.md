# Chapter 7 — Day-to-day after install

*Teammate Guide > Chapter 7: Day-to-day after install*

> Reference chapter — 5 minutes to skim. Look up sections as you need them.

Once chapter 4 has worked once, every following day looks like this.

---

## Open the project for the day {#starting}

**Run in: WSL2 Ubuntu terminal**

```
cd ~/projects/KhanaBazaar
./scripts/dev.sh start
```

**What you should see:**

```
Starting backend...
backend started (pid 12345) -> .dev/logs/backend.log
Starting celery...
celery started (pid 12346) -> .dev/logs/celery.log
Starting frontend...
frontend started (pid 12347) -> .dev/logs/frontend.log
Starting log_viewer...
log_viewer started (pid 12348) -> .dev/logs/log_viewer.log

All services up.
  Backend:    http://localhost:8000  (docs: /docs)
  Frontend:   http://localhost:3000
  Log viewer: http://localhost:8001
```

That is the entire start-of-day routine. Open the three browser tabs from chapter 4:

- `http://localhost:3000` — the KhanaBazaar frontend
- `http://localhost:8000/docs` — the *[Swagger](./appendix-glossary.md#swagger)* *[API](./appendix-glossary.md#api)* docs
- `http://localhost:8001` — the log viewer

---

## Stop for the day {#stopping}

**Run in: WSL2 Ubuntu terminal**

```
./scripts/dev.sh stop
```

**What you should see:** four `Stopping <service> (pid ...)...` lines, one for each *[backend](./appendix-glossary.md#backend)* process.

The *[Docker](./appendix-glossary.md#docker)* *[PostgreSQL](./appendix-glossary.md#postgresql)* and *[Redis](./appendix-glossary.md#redis)* *[containers](./appendix-glossary.md#container)* keep running in the background — they use very little memory and restart quickly.

Optional: to stop the *[database](./appendix-glossary.md#database)* and *[cache](./appendix-glossary.md#cache)* as well (useful if you are short on RAM):

**Run in: WSL2 Ubuntu terminal**

```
./scripts/dev.sh stop --all
```

---

## Status and logs {#status-and-logs}

Check what is running:

**Run in: WSL2 Ubuntu terminal**

```
./scripts/dev.sh status
```

**What you should see:** the status of each service — `running`, `stopped`, or `not started`.

---

Follow a live log stream:

**Run in: WSL2 Ubuntu terminal**

```
./scripts/dev.sh logs backend
```

This live-tails the named log. The service name can be `backend`, `celery`, `frontend`, `ngrok`, or `log_viewer`. Press `Ctrl+C` to stop following.

**What you should see:** a stream of log lines from that service, updating in real-time as activity happens.

Tip: use the log viewer at `http://localhost:8001` for tabbed logs, or `./scripts/dev.sh logs <service>` for a live tail in the terminal.

---

## Pull new code {#pull-new-code}

When you arrive and teammates have merged *[commits](./appendix-glossary.md#commit)* to main:

**Run in: WSL2 Ubuntu terminal**

```
git pull
```

Then check what changed:

- **If backend files changed** (anything under `backend/app/`):

  **Run in: WSL2 Ubuntu terminal**

  ```
  cd backend/app
  uv sync
  uv run alembic upgrade head
  cd ../..
  ```

  `uv sync` downloads any new *[dependencies](./appendix-glossary.md#dependency)`. `alembic upgrade head` applies any new *[migrations](./appendix-glossary.md#migration)*.

- **If frontend files changed** (anything under `frontend/`):

  **Run in: WSL2 Ubuntu terminal**

  ```
  cd frontend
  npm install
  cd ..
  ```

  *[npm](./appendix-glossary.md#npm)* downloads new *[dependencies](./appendix-glossary.md#dependency)*.

Then restart the app:

**Run in: WSL2 Ubuntu terminal**

```
./scripts/dev.sh restart
```

---

## When to re-seed {#re-seed}

Re-seed only when the demo data feels broken or the engineer tells you to.

**Run in: WSL2 Ubuntu terminal**

```
cd backend/app
uv run python scripts/seed_database.py
cd ../..
```

The script is idempotent — safe to re-run without duplicating data.

---

## Updating tools {#updating-tools}

As weeks pass, minor updates arrive for the tools you use.

**Docker Desktop:** The built-in updater notifies you in the system tray. Click and apply.

**WSL:**

**Run in: PowerShell**

```
wsl --update
```

**Node:**

**Run in: WSL2 Ubuntu terminal**

```
nvm install --lts
nvm alias default <new-version>
```

Replace `<new-version>` with the version number that `nvm install --lts` printed.

**uv:**

**Run in: WSL2 Ubuntu terminal**

```
uv self update
```

---

## Reading logs to find your own answers {#reading-logs}

The *[backend](./appendix-glossary.md#backend)* uses four severity levels in its logs. Before reaching out, skim the logs for context.

- **`INFO`** — normal activity, nothing to worry about.
- **`WARNING`** — suspicious but not broken.
- **`ERROR`** — a real problem.
- **`CRITICAL`** — system-level failure, app cannot continue.

Examples:

```
INFO     2026-05-08 10:00:01 — request started: GET /api/v1/stores
WARNING  2026-05-08 10:00:02 — slow query (>500ms): SELECT * FROM orders ...
ERROR    2026-05-08 10:00:03 — psycopg2.OperationalError: could not connect
CRITICAL 2026-05-08 10:00:04 — Celery broker unreachable
```

Most errors have an explanation or stack trace on the following lines. Start there. If you are stuck, use the Slack template in [Chapter 6](./06-troubleshooting.md#nothing-here-matches).

---

## Reset to a clean slate {#reset-everything}

> **This deletes all your demo data.** Use only when nothing else has worked. Takes about 5 minutes.

**Run in: WSL2 Ubuntu terminal**

```
./scripts/dev.sh stop --all
docker compose down -v
docker compose up -d
cd backend/app
uv run alembic upgrade head
uv run python scripts/seed_database.py
cd ../..
./scripts/dev.sh start
```

This stops the app, deletes the *[containers](./appendix-glossary.md#container)* and their data, re-creates them fresh, rebuilds the *[database](./appendix-glossary.md#database)* schema, loads demo data, and restarts the app.

---

← [Previous: Chapter 6 — When things break](./06-troubleshooting.md)  |  Next: [Appendix — Phone testing (optional)](./appendix-mobile-ngrok.md) →
