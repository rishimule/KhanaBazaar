# Render.com Deployment Guide

End-to-end guide for deploying Khana Bazaar to [Render](https://render.com) using the Blueprint at `/render.yaml` (repo root). The Blueprint is the single source of truth — every service, env var, and wiring rule lives there. This document explains how to consume it.

---

## 1. Overview

Render Blueprint provisions five resources from one file:

| Resource (Blueprint name)   | Type                  | Purpose                                  |
|-----------------------------|-----------------------|------------------------------------------|
| `khanabazaar-db`            | Postgres 15           | Primary data store                       |
| `khanabazaar-redis`         | Key Value (Redis)     | Celery broker + cache                    |
| `khanabazaar-api`           | Web (Python)          | FastAPI backend (`backend/app`)          |
| `khanabazaar-worker`        | Background worker     | Celery worker (same codebase)            |
| `khanabazaar-web`           | Web (Node)            | Next.js frontend (`frontend`)            |

All services run in `singapore` region on `starter` plans (Postgres on `basic-256mb`). `autoDeploy: true` on all three services — push to `main` and Render rebuilds.

---

## 2. Architecture

```
                    ┌───────────────────────┐
  Customer ───►     │  khanabazaar-web      │     (Next.js SSR, port $PORT)
   (browser)        │  Node 20, public URL  │
                    └──────────┬────────────┘
                               │ HTTPS (NEXT_PUBLIC_API_URL)
                               ▼
                    ┌───────────────────────┐
                    │  khanabazaar-api      │     (FastAPI, port $PORT)
                    │  Python 3.12, public  │
                    └──────┬─────────┬──────┘
                           │         │
            Render private │         │ Render private
              network      │         │   network
                           ▼         ▼
              ┌────────────────┐  ┌──────────────────────┐
              │ khanabazaar-db │  │ khanabazaar-redis    │
              │ Postgres 15    │  │ keyvalue (Redis)     │
              └────────────────┘  └──────────┬───────────┘
                       ▲                     │
                       │                     │
                       │       ┌─────────────┴────────────┐
                       └───────┤ khanabazaar-worker        │
                               │ Celery, no public ingress │
                               └───────────────────────────┘
```

Worker shares Postgres + Redis with API. Frontend never talks to Postgres or Redis directly — only through the API.

---

## 3. Pre-deployment checklist

- GitHub repo connected to Render (Account Settings → GitHub → grant repo access).
- Branch to deploy is `main` (Blueprint hardcodes this — change `branch:` in `render.yaml` if you fork).
- `backend/app/build.sh` and `backend/app/predeploy.sh` exist and are executable (`chmod +x`).
- Resend account: API key + verified sender domain (production email). Values land in `RESEND_API_KEY` and `RESEND_FROM_EMAIL` (both `sync: false`).
- Strong randomness for secrets — Render auto-generates `JWT_SECRET` and `OTP_PEPPER` via `generateValue: true`, but if you ever rotate manually, use `openssl rand -hex 32`.
- (Optional) Custom domain registered, DNS access available for CNAME setup.

---

## 4. First-time deployment

1. Commit `render.yaml`, `backend/app/build.sh`, `backend/app/predeploy.sh` to `main` and push.
2. Render dashboard → **New + → Blueprint**.
3. Pick the GitHub repo, branch `main`. Render parses `render.yaml` and lists every resource it will create.
4. Render prompts for `sync: false` secrets:
   - On `khanabazaar-api`: `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `FRONTEND_ORIGIN`
   - On `khanabazaar-worker`: `RESEND_API_KEY`, `RESEND_FROM_EMAIL`
   - On `khanabazaar-web`: `NEXT_PUBLIC_API_URL` (paste a stub like `https://khanabazaar-api.onrender.com` — fill exact value once API gets its URL)
5. Click **Apply**. Provisioning order: Postgres → Redis → API + Worker + Frontend in parallel. First build runs 5–10 min.
6. After API's first deploy succeeds, copy its public URL (`https://khanabazaar-api.onrender.com`):
   - `khanabazaar-web` → Environment → set `NEXT_PUBLIC_API_URL` to that URL → **Manual Deploy**. Required because `NEXT_PUBLIC_*` is inlined at **build** time.
   - `khanabazaar-api` → Environment → set `FRONTEND_ORIGIN` to the frontend's public URL (`https://khanabazaar-web.onrender.com`) → redeploy so CORS picks it up.
7. Verify: `curl https://khanabazaar-api.onrender.com/health` returns `{"status":"ok","environment":"production"}`.

---

## 5. Service-by-service env vars

Source: `/render.yaml`. Bold = secret you supply manually. Italic = auto-injected by Render.

### 5.1 `khanabazaar-api` (FastAPI)

| Key                    | Value / Source                                           | Notes                                  |
|------------------------|----------------------------------------------------------|----------------------------------------|
| `PYTHON_VERSION`       | `3.12`                                                   | Build-time pin                         |
| `PROJECT_NAME`         | `Khana Bazaar API`                                       | App title                              |
| `ENVIRONMENT`          | `production`                                             | Read by `core/config.py`               |
| `DATABASE_URL`         | *fromDatabase `khanabazaar-db.connectionString`*         | Auto. Rewritten to `postgresql+asyncpg://` at runtime |
| `REDIS_URL`            | *fromService keyvalue `khanabazaar-redis.connectionString`* | Auto                                |
| `JWT_SECRET`           | *generateValue: true*                                    | Generated once, persisted              |
| `JWT_EXPIRES_HOURS`    | `24`                                                     |                                        |
| `OTP_PEPPER`           | *generateValue: true*                                    | Generated once, persisted              |
| `OTP_TTL_SECONDS`      | `600`                                                    |                                        |
| `OTP_MAX_ATTEMPTS`     | `5`                                                      |                                        |
| `OTP_RESEND_COOLDOWN`  | `60`                                                     |                                        |
| `OTP_MAX_PER_HOUR`     | `5`                                                      |                                        |
| `EMAIL_PROVIDER`       | `resend`                                                 | `console` only for debugging           |
| **`RESEND_API_KEY`**   | sync: false                                              | From Resend dashboard                  |
| **`RESEND_FROM_EMAIL`**| sync: false                                              | Verified sender, e.g. `noreply@yourdomain.com` |
| **`FRONTEND_ORIGIN`**  | sync: false                                              | Public frontend URL — used for CORS    |

### 5.2 `khanabazaar-worker` (Celery)

Shares config with API. Render wires `JWT_SECRET` and `OTP_PEPPER` from the API service via `fromService.envVarKey`, so both processes use identical signing material.

| Key                    | Value / Source                                           |
|------------------------|----------------------------------------------------------|
| `PYTHON_VERSION`       | `3.12`                                                   |
| `ENVIRONMENT`          | `production`                                             |
| `DATABASE_URL`         | *fromDatabase `khanabazaar-db`*                          |
| `REDIS_URL`            | *fromService `khanabazaar-redis`*                        |
| `JWT_SECRET`           | *fromService web `khanabazaar-api.JWT_SECRET`*           |
| `OTP_PEPPER`           | *fromService web `khanabazaar-api.OTP_PEPPER`*           |
| `EMAIL_PROVIDER`       | `resend`                                                 |
| **`RESEND_API_KEY`**   | sync: false                                              |
| **`RESEND_FROM_EMAIL`**| sync: false                                              |

Worker does **not** receive `OTP_TTL_SECONDS`, `OTP_MAX_ATTEMPTS`, etc. — those settings only matter at the request boundary.

### 5.3 `khanabazaar-web` (Next.js)

| Key                     | Value / Source                                 | Notes                                 |
|-------------------------|------------------------------------------------|---------------------------------------|
| `NODE_VERSION`          | `20`                                           |                                       |
| **`NEXT_PUBLIC_API_URL`** | sync: false                                  | Inlined at build time. Re-deploy after editing. |

Why not auto-wire from the API service? Render's `fromService.host` returns the **private** hostname; browsers can't reach it. The public `onrender.com` URL is only known after first deploy, so this stays manual.

### 5.4 `khanabazaar-db` (Postgres)

Managed. No manual env vars. Render exposes:
- `connectionString` (consumed by `DATABASE_URL` on API + worker)
- Internal/external connection strings in dashboard (use external for one-off `psql` from your laptop)

### 5.5 `khanabazaar-redis` (Key Value)

Managed. `ipAllowList: []` blocks all external traffic — only services in your Render account can connect. `maxmemoryPolicy: noeviction` (Celery requires this; eviction would silently drop queued tasks).

---

## 6. Build & start commands

All come from `render.yaml`. Verify before changing.

### Backend API (`khanabazaar-api`)
- `rootDir`: `backend/app`
- Build: `./build.sh` — installs `uv`, runs `uv sync --frozen --no-dev`
- Pre-deploy: `./predeploy.sh` — runs `uv run alembic upgrade head` before traffic switches to new revision
- Start: `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check: `GET /health`

### Worker (`khanabazaar-worker`)
- `rootDir`: `backend/app`
- Build: `./build.sh` (same script as API)
- Start: `uv run celery -A app.core.celery_app worker --loglevel=info --concurrency 2`
- No pre-deploy step (migrations are API's job).

### Frontend (`khanabazaar-web`)
- `rootDir`: `frontend`
- Build: `npm ci && npm run build`
- Start: `npm run start -- -p $PORT`

`build.sh` template (lives at `backend/app/build.sh`):
```bash
#!/usr/bin/env bash
set -o errexit
pip install --upgrade pip
pip install uv
uv sync --frozen --no-dev
```

`predeploy.sh` template:
```bash
#!/usr/bin/env bash
set -o errexit
uv run alembic upgrade head
```

---

## 7. Database migrations on deploy

`preDeployCommand` runs `alembic upgrade head` after a successful build but **before** Render flips traffic to the new revision. Atomicity guarantees:

- Migration failure → deploy aborts, old revision stays live, no downtime.
- Migration success → new code goes live with schema already in place.

Pitfalls:

- **Long migrations**: pre-deploy has a Render-imposed time limit. Migrations rewriting millions of rows or building giant indexes will time out. Run those out-of-band from the API service's **Shell** tab using `uv run alembic upgrade <revision>`.
- **Irreversible changes**: dropping columns or tables can't be rolled back by the "Rollback" button alone — code rolls back but schema doesn't. Use expand/contract: ship a migration that adds the new shape, deploy, backfill, then a later release drops the old shape.
- **Locking**: `ALTER TABLE` on Postgres takes ACCESS EXCLUSIVE locks. For hot tables, prefer `CREATE INDEX CONCURRENTLY` and explicit transactional batching.

---

## 8. Rolling out updates

| Action               | How                                                                 |
|----------------------|---------------------------------------------------------------------|
| Deploy latest commit | Push to `main` (autoDeploy on) — Render rebuilds API + worker + web |
| Deploy a different commit | Service → **Manual Deploy → Deploy specific commit**           |
| Roll back            | Service → **Deploys** tab → previous deploy → **Rollback**          |
| Pause auto-deploy    | Service → Settings → Auto-Deploy → Off (e.g. during a freeze)       |

Every push that changes `frontend/**` triggers a frontend rebuild and a new bundle. Backend changes rebuild API + worker. Render does not run other services' builds when only one service's `rootDir` is touched.

---

## 9. Custom domain & TLS

1. Service → **Settings → Custom Domains → Add Custom Domain**.
2. Render shows a CNAME target (e.g. `khanabazaar-web.onrender.com`). Add this as a CNAME record at your DNS provider (apex domain users: use ALIAS/ANAME or Render's static IP).
3. Render auto-provisions a Let's Encrypt cert and renews it. TLS is on by default — no config needed.
4. After the API gets its custom domain (e.g. `api.khanabazaar.com`):
   - Update `NEXT_PUBLIC_API_URL` on `khanabazaar-web` and **redeploy** (build-time inline).
   - Update `FRONTEND_ORIGIN` on `khanabazaar-api` to the frontend's custom domain.

---

## 10. CORS

Currently `backend/app/src/app/__init__.py` hardcodes:

```python
allow_origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
],
```

This **blocks production traffic** from `khanabazaar-web.onrender.com`. Two options before going live:

**Option A — quick fix**: append the deployed frontend URL to `allow_origins`:
```python
allow_origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://khanabazaar-web.onrender.com",
    # plus any custom domain
],
```

**Option B — env-driven (preferred)**: read from `FRONTEND_ORIGIN` (already wired in `render.yaml` as `sync: false`):

1. Add `FRONTEND_ORIGIN: str = ""` to `backend/app/src/app/core/config.py`.
2. In `backend/app/src/app/__init__.py`:
   ```python
   origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
   if settings.FRONTEND_ORIGIN:
       origins.append(settings.FRONTEND_ORIGIN)
   app.add_middleware(CORSMiddleware, allow_origins=origins, ...)
   ```
3. Set `FRONTEND_ORIGIN` in Render dashboard to the frontend's public URL.

Option B is required for any proper multi-environment setup (staging vs. prod).

---

## 11. Logs & debugging

- **Live logs**: Service → **Logs** tab — streaming, searchable, last 7 days retained on `starter`.
- **CLI tail**: install [Render CLI](https://render.com/docs/cli), then `render logs --resources khanabazaar-api --tail`.
- **Shell access**: Service → **Shell** tab opens a TTY in the running container. Useful for `uv run alembic ...`, ad-hoc Python REPL, or checking `env`.

Common issues:

| Symptom                                          | Likely cause / fix                                                              |
|--------------------------------------------------|---------------------------------------------------------------------------------|
| API 500 on every request                         | `DATABASE_URL` driver mismatch — `core/config.py` rewrites `postgres://` to `postgresql+asyncpg://`; verify the validator runs |
| Pre-deploy fails with `alembic.util.CommandError` | Migration head divergence — rebase migration history on `main` and force a new revision |
| Worker logs `kombu.exceptions.OperationalError` on boot | Redis cold-start lag; first connection retries — usually self-heals within ~30 s. Persists? Check `REDIS_URL` value matches `khanabazaar-redis` |
| Frontend hits `localhost:8000` in production     | `NEXT_PUBLIC_API_URL` set after build — **redeploy** the frontend; Next.js inlines `NEXT_PUBLIC_*` at build time |
| Browser console: CORS error                      | `FRONTEND_ORIGIN` not set, or CORS code still hardcodes localhost — see §10     |
| API boot crash: `ValidationError JWT_SECRET field required` | `generateValue` failed to populate (rare) — set manually via dashboard with `openssl rand -hex 32` |

---

## 12. Scaling

| Component          | Vertical                              | Horizontal                                         |
|--------------------|---------------------------------------|----------------------------------------------------|
| API web service    | Settings → Instance Type (starter → standard → pro) | Settings → Instance Count (>1 enables load balancing) |
| Celery worker      | Same                                  | Increase Instance Count for more parallel task processing |
| Postgres           | Plan upgrade (basic-256mb → basic-1gb → pro-*)  | Read replicas on `pro` and above              |
| Redis              | Plan upgrade                          | Single-node only on Render Key Value               |

Worker concurrency is set in `render.yaml` (`--concurrency 2`). Bump in the Blueprint, not via dashboard, so the change is version-controlled.

---

## 13. Cost expectations

Render pricing changes regularly. Treat the Blueprint plans (`starter` web/worker, `basic-256mb` Postgres, `starter` Key Value) as a starting point and check current rates at <https://render.com/pricing>. Free tiers exist for trial but Postgres free expires after 30 days and free web services sleep after inactivity.

---

## 14. Disaster recovery

- **Postgres backups**: Render snapshots Postgres daily on paid plans (basic-256mb included). Service → **Backups** tab → restore creates a new database from a snapshot. Repoint `DATABASE_URL` (or update `render.yaml` `databases.name`) and redeploy.
- **Point-in-time recovery**: available on `pro` Postgres plans.
- **Manual backup**: from Shell tab on API service:
  ```bash
  pg_dump "$DATABASE_URL" > /tmp/backup.sql
  ```
  Download via Render CLI's `render exec` or pipe to S3.
- **Redis**: ephemeral — Celery queues survive restarts because `maxmemoryPolicy: noeviction`, but treat Redis as cache only. No app state should require Redis durability.
- **Code**: source of truth is GitHub. Render rebuilds reproducibly from any commit.

Recommended cadence: rely on Render's daily snapshots for Postgres + a weekly manual `pg_dump` to off-platform storage (S3, R2) for paranoia.

---

## 15. Local testing of production build

Sanity-check the production codepath before pushing.

### Backend
```bash
cd backend/app
ENVIRONMENT=production \
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar \
REDIS_URL=redis://localhost:6379/0 \
JWT_SECRET=$(openssl rand -hex 32) \
OTP_PEPPER=$(openssl rand -hex 16) \
EMAIL_PROVIDER=console \
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build
NEXT_PUBLIC_API_URL=http://localhost:8000 npm start
```

This catches build-time issues (TypeScript errors, missing env vars inlined into the bundle, Alembic migration drift) without burning a Render deploy.

---

## 16. References

- [Render Blueprint spec](https://render.com/docs/blueprint-spec)
- [Deploy FastAPI on Render](https://render.com/docs/deploy-fastapi)
- [Deploy Next.js on Render](https://render.com/docs/deploy-nextjs-app)
- [Deploy Celery worker](https://render.com/docs/deploy-celery)
- [Monorepo support (`rootDir`)](https://render.com/docs/monorepo-support)
- [Pre-deploy commands](https://render.com/docs/deploys#pre-deploy-command)
- [Environment variables](https://render.com/docs/configure-environment-variables)
- [Render pricing](https://render.com/pricing)
