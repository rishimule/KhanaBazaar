# Chapter 4 — Run the app for the first time

*Teammate Guide > Chapter 4: Run the app for the first time*

> Estimated time: about 25 minutes for the first run. Most of it is downloads.

This chapter walks you through starting two background services in *[containers](./appendix-glossary.md#container)*, installing the *[backend](./appendix-glossary.md#backend)* and *[frontend](./appendix-glossary.md#frontend)* dependencies, building the empty *[database](./appendix-glossary.md#database)* tables, loading demo data using *[seed data](./appendix-glossary.md#seed-data)*, and finally launching the full app so you can see it working in a browser.

---

## 1. Start Docker Desktop

Click the Docker Desktop icon in the Start menu. Wait until the whale icon appears in the system tray (bottom-right) AND the Docker Desktop window says "Docker Desktop is running" (Settings → General).

[Screenshot: Docker Desktop window showing "Engine running" status]

**If it fails.** See [./06-troubleshooting.md#docker-wont-start](./06-troubleshooting.md#docker-wont-start).

---

## 2. Bring up Postgres and Redis

**Run in: WSL2 Ubuntu terminal**

```
cd ~/projects/KhanaBazaar
docker compose up -d
```

This downloads two pre-built images and runs them as *[containers](./appendix-glossary.md#container)* — *[PostgreSQL](./appendix-glossary.md#postgresql)* (the *[database](./appendix-glossary.md#database)*) and *[Redis](./appendix-glossary.md#redis)* (the *[cache](./appendix-glossary.md#cache)* and *[Celery](./appendix-glossary.md#celery)* broker). Wait time: 1–3 minutes on first run while images download (about 400 MB).

**What you should see:**

```
[+] Pulling 14/14
 ✔ postgres Pulled
 ✔ redis Pulled
[+] Running 2/2
 ✔ Container khanabazaar-postgres  Started
 ✔ Container khanabazaar-redis     Started
```

**Wait for Postgres to finish starting before moving to the next step.** Running migrations against a half-started database fails with `connection refused`. Run this command and repeat it until the output shows `localhost:5432 - accepting connections`. Usually takes 5–20 seconds.

**Run in: WSL2 Ubuntu terminal**

```
docker compose exec postgres pg_isready -U postgres -d khanabazaar
```

**What you should see:**

```
localhost:5432 - accepting connections
```

Verify both containers are running:

**Run in: WSL2 Ubuntu terminal**

```
docker compose ps
```

**What you should see:** two rows — `khanabazaar-postgres` and `khanabazaar-redis` — both with `STATUS` showing `Up <duration>`.

**If it fails.** For "port already in use" errors, see [./06-troubleshooting.md#docker-compose-port-in-use](./06-troubleshooting.md#docker-compose-port-in-use). For download failures, see [./06-troubleshooting.md#docker-compose-pulls-fail](./06-troubleshooting.md#docker-compose-pulls-fail).

---

## 3. Install backend dependencies

**Run in: WSL2 Ubuntu terminal**

```
cd backend/app
uv sync
```

This downloads and installs every Python *[dependency](./appendix-glossary.md#dependency)* the backend needs. Subsequent runs take seconds; first run takes 2–5 minutes.

**What you should see:** a long list of `+ <package>==<version>` lines, ending with `Resolved <N> packages` and `Installed <N> packages`.

**If it fails.** See [./06-troubleshooting.md#uv-sync-fails](./06-troubleshooting.md#uv-sync-fails).

---

## 4. Build the database tables

**Run in: WSL2 Ubuntu terminal**

```
uv run alembic upgrade head
```

This runs *[migrations](./appendix-glossary.md#migration)* — scripts that build empty tables in your freshly-created database, ready for data.

**What you should see:**

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> abc123, initial schema
INFO  [alembic.runtime.migration] Running upgrade abc123 -> def456, add stores
```

The output ends with the most recent migration name. There should be no `ERROR` lines.

**If it fails.** See [./06-troubleshooting.md#alembic-not-up-to-date](./06-troubleshooting.md#alembic-not-up-to-date).

---

## 5. Load demo data

**Run in: WSL2 Ubuntu terminal**

```
uv run python scripts/seed_database.py
```

This fills the database with sample products, stores, and the demo accounts you will use in chapter 5. The script is idempotent — safe to re-run without duplicating data.

**What you should see:** a series of `Creating ...` and `Updating ...` lines, ending with `Seed complete.` (exact wording may differ).

**If it fails.** See [./06-troubleshooting.md#seed-script-crashes](./06-troubleshooting.md#seed-script-crashes).

---

## 6. Install frontend dependencies

**Run in: WSL2 Ubuntu terminal**

```
cd ../../frontend
npm install
```

*[npm](./appendix-glossary.md#npm)* downloads every JavaScript library the frontend needs. Wait time: 2–4 minutes on first run.

**What you should see:** a progress bar, then `added <N> packages, and audited <N> packages in <time>`. A few `npm warn` lines are normal — `npm error` lines are not.

**If it fails.** See [./06-troubleshooting.md#npm-install-fails](./06-troubleshooting.md#npm-install-fails).

---

## 7. Start everything with one command

**Run in: WSL2 Ubuntu terminal**

```
cd ..
./scripts/dev.sh start
```

This single command starts four processes: the backend server on *[port](./appendix-glossary.md#port)* 8000, the *[Celery](./appendix-glossary.md#celery)* worker for background tasks, the frontend on port 3000, and a log viewer on port 8001. Each process writes its output to a log file under `.dev/logs/`.

**What you should see:**

*The first 10–30 seconds print Docker output (`Bringing up Postgres + Redis...`, `[+] Running`...) before the `Starting <service>` lines arrive. This is normal — the script confirms the database is ready before it boots the backend.*

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

**If it fails.** For general startup failures, see [./06-troubleshooting.md#dev-sh-start-fails](./06-troubleshooting.md#dev-sh-start-fails). For port conflicts, see [./06-troubleshooting.md#port-3000-in-use](./06-troubleshooting.md#port-3000-in-use).

---

## 8. Verify in the browser

1. **Click in: web browser** — open `http://localhost:3000`.

   **What you should see:** the KhanaBazaar storefront with a list of stores. If you see an empty page, wait 10 seconds — the *[frontend](./appendix-glossary.md#frontend)* is compiling on the first request.

   [Screenshot: KhanaBazaar storefront with store cards in Chrome]

2. **Click in: web browser** — open `http://localhost:8000/docs`.

   **What you should see:** the *[Swagger](./appendix-glossary.md#swagger)* API documentation page with a long list of routes grouped under `auth`, `catalog`, `stores`, and more.

   [Screenshot: Swagger UI showing /api/v1 routes]

3. **Click in: web browser** — open `http://localhost:8001`.

   **What you should see:** the log viewer with four tabs across the top: `backend`, `celery`, `frontend`, `ngrok`.

   [Screenshot: log viewer with backend tab active]

---

## 9. Stop the app for the day

**Run in: WSL2 Ubuntu terminal**

```
./scripts/dev.sh stop
```

**What you should see:** four or five `Stopping <service> (pid ...)` lines (one per running service — services that were not started print `<service> not running` instead, which is fine).

The *[Docker](./appendix-glossary.md#docker)* Postgres and Redis *[containers](./appendix-glossary.md#container)* keep running in the background after this — they use little RAM and restart quickly. To stop them as well, run:

**Run in: WSL2 Ubuntu terminal**

```
./scripts/dev.sh stop --all
```

See [Chapter 7 — Day-to-day after install](./07-daily-use.md#stopping) for the full daily workflow.

---

← [Previous: Chapter 3 — Google Maps API keys (optional)](./03-google-maps-keys.md)  |  Next: [Chapter 5 — Demo accounts and login flow](./05-demo-logins.md) →
