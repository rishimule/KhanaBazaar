# Deploying Khana Bazaar to Render

End-to-end guide for hosting the Khana Bazaar stack (FastAPI + Celery + Postgres + Redis + Next.js) on [Render](https://render.com) by linking the GitHub repository. Uses Render's [Blueprint](https://render.com/docs/blueprint-spec) (Infrastructure-as-Code) so every service is provisioned from a single `render.yaml`.

---

## 1. What gets deployed

| Render Resource | Khana Bazaar Component | Plan (suggested) |
|----------------|------------------------|------------------|
| Postgres database | Primary data store | `basic-256mb` (or `free` for trial) |
| Key Value (Redis) | Celery broker + cache | `starter` (or `free`) |
| Web Service (Python) | FastAPI API (`backend/app`) | `starter` |
| Background Worker (Python) | Celery worker | `starter` |
| Web Service (Node) | Next.js frontend (`frontend`) | `starter` |

Render's free Postgres expires after 30 days and free web services sleep after 15 minutes of inactivity. Use paid plans for anything customer-facing.

---

## 2. Prerequisites

1. Push the repo to GitHub (public or private — Render supports both).
2. Sign up at [render.com](https://dashboard.render.com/register) and connect your GitHub account: **Account Settings → GitHub → Connect**. Grant access to the `KhanaBazaar` repo.
3. Make sure the branch you want to deploy (`main` recommended) is up to date.

---

## 3. Repo prep (one-time)

A few files must exist before the Blueprint will build successfully.

### 3.1 Backend build script — `backend/app/build.sh`

```bash
#!/usr/bin/env bash
set -o errexit

# Install uv (Render images don't ship with it)
pip install --upgrade pip
pip install uv

# Install project dependencies (locked) into the active Python env
uv sync --frozen --no-dev
```

Make it executable:

```bash
chmod +x backend/app/build.sh
git add backend/app/build.sh
```

### 3.2 Backend pre-deploy script — `backend/app/predeploy.sh`

Runs Alembic migrations on every deploy, before the new revision becomes live.

```bash
#!/usr/bin/env bash
set -o errexit
uv run alembic upgrade head
```

```bash
chmod +x backend/app/predeploy.sh
```

### 3.3 DATABASE_URL driver fix

Render's Postgres `connectionString` starts with `postgres://`, but SQLModel/asyncpg requires `postgresql+asyncpg://`. The cleanest fix is to read both shapes in `backend/app/src/app/core/config.py` (rewrite at runtime) **or** set `DATABASE_URL` manually in the Render dashboard with the asyncpg prefix copied from the database's "Internal Database URL".

Recommended runtime rewrite (idempotent):

```python
# in core/config.py, after loading DATABASE_URL
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
```

### 3.4 Next.js — bind to Render's `$PORT`

Render injects `PORT`. Next.js reads it automatically when started with `next start -p $PORT`. The Blueprint below sets that explicitly, so no code change is required.

### 3.5 CORS allow-list (required before deploy)

`backend/app/src/app/__init__.py` currently hardcodes CORS origins to `localhost:3000` / `127.0.0.1:3000`. Production calls from `khanabazaar-web.onrender.com` will be blocked. Either:

- Add the deployed frontend URL to the `allow_origins` list directly, **or**
- Promote the list to an env var (e.g. `FRONTEND_ORIGIN`) and read it from `settings`. The Blueprint already exposes `FRONTEND_ORIGIN` as a `sync: false` secret on the API service for this purpose.

---

## 4. The Blueprint — `render.yaml`

Place this file at the **repo root** (`/render.yaml`).

```yaml
# Khana Bazaar — Render Blueprint
# Single source of truth for every Render resource.

databases:
  - name: khanabazaar-db
    plan: basic-256mb        # use `free` for a 30-day trial
    databaseName: khanabazaar
    user: khanabazaar
    postgresMajorVersion: "15"

services:
  # ── Redis (Celery broker + cache) ────────────────────────────────────
  - type: keyvalue
    name: khanabazaar-redis
    plan: starter            # use `free` for trial
    region: singapore        # closest to India; pick what fits
    ipAllowList: []          # internal-only; only Render services can reach it
    maxmemoryPolicy: noeviction

  # ── FastAPI backend ──────────────────────────────────────────────────
  - type: web
    name: khanabazaar-api
    runtime: python
    plan: starter
    region: singapore
    rootDir: backend/app
    branch: main
    autoDeploy: true
    buildCommand: ./build.sh
    preDeployCommand: ./predeploy.sh
    startCommand: uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    envVars:
      - key: PYTHON_VERSION
        value: "3.12"
      - key: PROJECT_NAME
        value: "Khana Bazaar API"
      - key: ENVIRONMENT
        value: production
      - key: DATABASE_URL
        fromDatabase:
          name: khanabazaar-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: keyvalue
          name: khanabazaar-redis
          property: connectionString
      - key: JWT_SECRET
        generateValue: true       # Render generates once, persists forever
      - key: JWT_EXPIRES_HOURS
        value: "24"
      - key: OTP_PEPPER
        generateValue: true
      - key: OTP_TTL_SECONDS
        value: "600"
      - key: OTP_MAX_ATTEMPTS
        value: "5"
      - key: OTP_RESEND_COOLDOWN
        value: "60"
      - key: OTP_MAX_PER_HOUR
        value: "5"
      - key: EMAIL_PROVIDER
        value: resend
      - key: RESEND_API_KEY
        sync: false               # paste in dashboard at first deploy
      - key: RESEND_FROM_EMAIL
        sync: false
      - key: FRONTEND_ORIGIN
        sync: false               # e.g. https://khanabazaar-web.onrender.com

  # ── Celery worker ────────────────────────────────────────────────────
  - type: worker
    name: khanabazaar-worker
    runtime: python
    plan: starter
    region: singapore
    rootDir: backend/app
    branch: main
    autoDeploy: true
    buildCommand: ./build.sh
    startCommand: uv run celery -A app.core.celery_app worker --loglevel=info --concurrency 2
    envVars:
      - key: PYTHON_VERSION
        value: "3.12"
      - key: ENVIRONMENT
        value: production
      - key: DATABASE_URL
        fromDatabase:
          name: khanabazaar-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: keyvalue
          name: khanabazaar-redis
          property: connectionString
      - key: JWT_SECRET
        fromService:
          type: web
          name: khanabazaar-api
          envVarKey: JWT_SECRET
      - key: OTP_PEPPER
        fromService:
          type: web
          name: khanabazaar-api
          envVarKey: OTP_PEPPER
      - key: EMAIL_PROVIDER
        value: resend
      - key: RESEND_API_KEY
        sync: false
      - key: RESEND_FROM_EMAIL
        sync: false

  # ── Next.js frontend ─────────────────────────────────────────────────
  - type: web
    name: khanabazaar-web
    runtime: node
    plan: starter
    region: singapore
    rootDir: frontend
    branch: main
    autoDeploy: true
    buildCommand: npm ci && npm run build
    startCommand: npm run start -- -p $PORT
    envVars:
      - key: NODE_VERSION
        value: "20"
      # NEXT_PUBLIC_* is inlined at BUILD time. fromService.host returns the
      # private hostname (browser can't reach it), so paste the API's public
      # URL in the dashboard. Re-deploy frontend after editing.
      - key: NEXT_PUBLIC_API_URL
        sync: false
```

Key Blueprint features used:

- **`fromDatabase`** wires `DATABASE_URL` to the Postgres connection string automatically.
- **`fromService` → `keyvalue`** wires the worker + API to the same Redis instance over Render's private network.
- **`generateValue: true`** lets Render mint `JWT_SECRET` and `OTP_PEPPER` once and reuse them (worker pulls the same value via `fromService.envVarKey`).
- **`sync: false`** marks values entered manually in the dashboard at first sync — used here for Resend secrets, `FRONTEND_ORIGIN`, and `NEXT_PUBLIC_API_URL` (the public API URL is only known after the API service first deploys, and Render does not expose a `publicUrl`/`externalUrl` Blueprint property).
- **`preDeployCommand`** runs `alembic upgrade head` before each new revision becomes live, so migrations are atomic with code rollouts.
- **`rootDir`** keeps the monorepo intact — each service builds only its own subtree.
- **`ipAllowList: []`** on Redis blocks all external traffic; only Render services in your account can connect.

---

## 5. Deploy via Blueprint

1. Commit `render.yaml`, `backend/app/build.sh`, `backend/app/predeploy.sh` and push to `main`.
2. In the Render dashboard: **New + → Blueprint**.
3. Pick the GitHub repo, branch `main`. Render parses `render.yaml` and shows every resource it will create.
4. Fill in the `sync: false` secrets when prompted on the API service (`RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `FRONTEND_ORIGIN`) and on the frontend (`NEXT_PUBLIC_API_URL`). The first apply lets you stub these — they can be replaced once URLs are known.
5. Click **Apply**. Render provisions Postgres → Redis → builds API + worker + frontend in parallel. First build takes 5–10 min.
6. After the API service finishes its first deploy, copy its public URL (e.g. `https://khanabazaar-api.onrender.com`):
   - Set `NEXT_PUBLIC_API_URL` on `khanabazaar-web` to that URL → trigger a manual redeploy (Next.js inlines this at build time).
   - Set `FRONTEND_ORIGIN` on `khanabazaar-api` to the frontend's public URL (e.g. `https://khanabazaar-web.onrender.com`) so CORS allows it.

---

## 6. Post-deploy checklist

- **Health check**: `curl https://khanabazaar-api.onrender.com/health` should return 200.
- **Migrations**: API logs should show `alembic upgrade head` ran in the pre-deploy phase.
- **Worker**: `khanabazaar-worker` logs should show `celery@... ready.` and a successful broker handshake to `khanabazaar-redis:6379`.
- **Frontend**: open `https://khanabazaar-web.onrender.com`, confirm storefront loads and `NEXT_PUBLIC_API_URL` points at the API service.
- **CORS**: open the browser devtools network tab; cross-origin calls from the frontend to the API must succeed.
- **Resend**: trigger an OTP signup; check Resend dashboard for the delivered email. Switch `EMAIL_PROVIDER` to `console` only if debugging.

---

## 7. Day-2 operations

| Task | How |
|------|-----|
| Trigger redeploy | Push to `main` (auto-deploy on) or **Manual Deploy → Deploy latest commit** |
| Run one-off command | Service → **Shell** tab → `uv run alembic ...` |
| Roll back | Service → **Deploys** → previous deploy → **Rollback** |
| Add env var | Edit `render.yaml` and push, or Service → **Environment** for one-offs |
| Scale | Service → **Settings → Instance Type / Instance Count** |
| Database backup | Postgres service → **Backups** (daily on paid plans) |
| Logs | Service → **Logs** (live tail) or `render logs` via the [Render CLI](https://render.com/docs/cli) |

---

## 8. Cost-saving tips

- Use the `free` plan on Postgres + Key Value while testing — promote to paid before launch (free Postgres is wiped after 30 days).
- Set `autoDeploy: false` on staging branches you don't want auto-redeploying.
- Move static assets to a CDN (Render Static Site is free) if frontend egress climbs.
- The Celery worker can run on `starter` ($7/mo) — bump only if queues back up.

---

## 9. Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| API boots but `/api/v1/health` 500s | `DATABASE_URL` still has `postgres://` prefix → confirm the runtime rewrite in `config.py` |
| Alembic fails in pre-deploy | DB user lacks privileges → recreate Postgres OR run `uv run alembic upgrade head` manually from Shell tab |
| Worker can't reach Redis | `REDIS_URL` wired to wrong service — check `fromService.name` matches the keyvalue service |
| Frontend hits `localhost:8000` in prod | `NEXT_PUBLIC_API_URL` not set at **build** time — Next.js inlines `NEXT_PUBLIC_*` during `npm run build`, so a redeploy is required after editing it |
| Free service sleeps | Move to `starter` ($7/mo) or hit the health endpoint from an uptime monitor |
| Build OOM on `uv sync` | Bump build instance via `plan: standard` or split heavy deps |

---

## 10. References

- [Render Blueprint spec](https://render.com/docs/blueprint-spec)
- [Deploy a FastAPI app](https://render.com/docs/deploy-fastapi)
- [Deploy a Next.js app](https://render.com/docs/deploy-nextjs-app)
- [Deploy a Celery worker](https://render.com/docs/deploy-celery)
- [Monorepo support](https://render.com/docs/monorepo-support)
- [Configure environment variables](https://render.com/docs/configure-environment-variables)
- [Pre-deploy commands](https://render.com/docs/deploys#pre-deploy-command)
