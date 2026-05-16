<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Local Setup

Get KhanaBazaar running on your machine in under 10 minutes. Stack: FastAPI + Next.js 16 + Postgres 15 (PostGIS 3.4) + Redis 7.

> The map / autocomplete features require Google Maps API keys. Skip them initially — the app falls back to manual address entry. When you need them, see [`google_maps_setup.md`](./google_maps_setup.md).

## 1. Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.12+ | Backend runtime |
| Node.js | 20 LTS+ | Frontend runtime |
| Docker + Docker Compose | latest | Postgres + Redis containers |
| `uv` | latest | Python package manager |
| `gh` CLI | latest | Optional, used for PR workflow |

Install `uv`:

```bash
# Option 1: pipx
pipx install uv

# Option 2: official installer
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify:

```bash
python3 --version    # 3.12.x
node --version       # v20+
docker --version
uv --version
```

## 2. Clone and structure

```bash
git clone https://github.com/<org>/KhanaBazaar.git
cd KhanaBazaar
```

Top-level layout: `backend/app/` (FastAPI + SQLModel + Alembic), `frontend/` (Next.js 16 App Router), `docs/` (this file lives here), `docker-compose.yml` (Postgres + Redis), `scripts/` (one-off CLI utilities).

## 3. Infrastructure

From the repo root:

```bash
docker compose up -d
```

Starts:

- `khanabazaar-postgres` — Postgres 15 + PostGIS 3.4 on `localhost:5432` (user `postgres`, password `password`, db `khanabazaar`)
- `khanabazaar-redis` — Redis 7 (alpine) on `localhost:6379`

### PostGIS upgrade (May 2026 onward)

The Postgres image was upgraded from `postgres:15` to `postgis/postgis:15-3.4` (binary-compatible drop-in that adds the PostGIS extension binaries). If you have an existing local volume from the plain image, recreate it once:

```bash
docker compose down -v
docker compose up -d
cd backend/app
uv run alembic upgrade head
```

Verify both containers are healthy:

```bash
docker compose ps
```

## 4. Backend

All commands below run from `backend/app/`.

### 4a. Environment

```bash
cd backend/app
cp .env.example .env
```

Required vars in `.env`:

| Var | Default in `.env.example` | Notes |
|-----|---------------------------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar` | Must use `+asyncpg` driver |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker + cache |
| `JWT_SECRET` | placeholder | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `OTP_PEPPER` | placeholder | Generate: `python -c "import secrets; print(secrets.token_hex(16))"` |
| `EMAIL_PROVIDER` | `console` | Keep as `console` in dev — OTP codes print to backend stdout |

Replace the two placeholder secrets with freshly generated values.

### 4b. Install + migrate

```bash
uv sync
uv run alembic upgrade head
```

### 4c. Optional seed data

Loads demo services, categories, products, stores, inventory, and a few users:

```bash
uv run python scripts/seed_database.py
```

Seed is idempotent — re-running upserts.

Product images use LoremFlickr CDN URLs (`https://loremflickr.com/400/400/<keyword>?lock=<n>`) drawn from `CATEGORY_IMAGE_POOLS` in `backend/app/src/app/db/_dev_seed_data.py` — 3 themed URLs per category, round-robin per subcategory. No local image files. If a new category is added without a `_CATEGORY_IMAGE_KEYWORDS` entry, seed fails loud with `KeyError: no image pool registered for category '<slug>'`. ProductCard renders the URL via raw `<img referrerPolicy="no-referrer">` and falls back to a category emoji glyph on load error.

### 4d. Run the API

```bash
uv run uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` for Swagger UI.

### 4e. Celery worker (separate terminal)

Background tasks (email dispatch, etc.) need a worker:

```bash
cd backend/app
uv run celery -A app.core.celery_app worker --loglevel=info
```

## 5. Frontend

From `frontend/`:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. Only env var is `NEXT_PUBLIC_API_URL` (defaults to `""` — empty means the browser sends `/api/v1/*` to the current origin and Next.js `rewrites()` proxies to the backend on `:8000`). For mobile testing over ngrok, see [section 6a](#6a-mobile-testing-via-ngrok-optional).

## 6. Verify the stack

1. **Swagger** — `http://localhost:8000/docs` loads.
2. **Public endpoint** — hit `GET /api/v1/products` from Swagger or:
   ```bash
   curl http://localhost:8000/api/v1/products
   ```
3. **OTP login** — on the frontend, request an OTP for any email. With `EMAIL_PROVIDER=console`, the 6-digit code appears in the uvicorn stdout log. Enter it on the frontend to receive a JWT.

## 6a. Mobile testing via ngrok (optional)

Open the in-progress webapp on a phone for real-device testing. ngrok must be installed and authenticated (`ngrok config add-authtoken <token>`) once.

```bash
./scripts/dev.sh start --tunnel
```

The script prints a public URL like `https://abc-123.ngrok-free.app`. Open it on the phone. ngrok serves a one-time interstitial warning page on first visit per device — click "Visit Site" — then the SPA loads.

How it works: ngrok forwards only port 3000 (the Next.js dev server). All `/api/v1/*` requests go same-origin to that URL and are proxied server-side by Next.js to the loopback FastAPI on :8000. The backend is never publicly reachable.

Useful while running:

```bash
./scripts/dev.sh tunnel-url     # print current public URL
./scripts/dev.sh status         # show services + tunnel URL
./scripts/dev.sh logs ngrok     # tail ngrok agent log
./scripts/dev.sh stop           # also kills the tunnel
```

Notes:

- The ngrok URL rotates on each restart on the free plan (unless you have a reserved domain configured in `~/.config/ngrok/ngrok.yml`). The frontend uses relative API paths, so this is harmless to the app — only the URL you type into the phone changes.
- First request through the tunnel may briefly 502 while Next.js compiles the entry route. Reload after a few seconds.
- `NEXT_PUBLIC_API_URL` in `frontend/.env.local` must remain an empty string. If it is set to an absolute URL like `http://localhost:8000`, the phone tries to reach the dev box's localhost and fails. The default in `.env.example` is already correct.

## 7. Test database

Tests run against a separate Postgres database, `khanabazaar_test` (see `backend/app/tests/conftest.py:25`). Create it once:

```bash
docker compose exec postgres createdb -U postgres khanabazaar_test
```

Run tests from `backend/app/`:

```bash
uv run pytest -v
```

Conftest drops and recreates schema per test, so no migrations needed for test DB.

## 8. Cheat sheet

Run from `backend/app/` unless noted.

```bash
# Lint + types
uv run ruff check .
uv run mypy .

# New migration after model change
uv run alembic revision --autogenerate -m "add foo column"
uv run alembic upgrade head

# Migration state
uv run alembic current
uv run alembic history

# Frontend (from frontend/)
npm run lint
npm run build
```

## 9. Troubleshooting

**Port already in use (5432, 6379, 8000, 3000)** — find the offender or stop the conflicting container:

```bash
lsof -i :5432
docker compose down
```

**`asyncpg.InvalidPasswordError` or `connection refused`** — Postgres isn't up yet. `docker compose ps` should show `postgres` running. Recreate with `docker compose up -d postgres`.

**`InvalidArgumentError: dialect 'postgres' is not supported`** — `DATABASE_URL` uses wrong scheme. Must be `postgresql+asyncpg://...`, not `postgres://` or `postgresql://`.

**`redis.exceptions.ConnectionError`** — Redis container not running. Check `docker compose ps`; if missing, `docker compose up -d redis`.

**OTP not arriving** — confirm `EMAIL_PROVIDER=console` in `backend/app/.env`. Code prints to the uvicorn console, not emailed. Restart uvicorn after editing `.env`.

**`alembic` says "Target database is not up to date"** — run `uv run alembic upgrade head`. If a migration is missing locally, pull main and re-sync.

**Migration drift after rebase** — inspect with `uv run alembic current` and `uv run alembic history`. If two heads exist, `alembic merge -m "merge heads" <rev1> <rev2>`.

**Tests fail with `database "khanabazaar_test" does not exist`** — create it (see section 7).

**Frontend can't reach API (localhost dev)** — confirm `NEXT_PUBLIC_API_URL` in `frontend/.env.local` is exactly `""` (empty string) and that the Next.js `rewrites()` block in `frontend/next.config.ts` proxies `/api/v1/:path*` to `http://localhost:8000/api/v1/:path*`. Restart `npm run dev` after editing either file.

**Phone can't reach API (ngrok tunnel)** — check `./scripts/dev.sh logs ngrok` for auth or quota errors. If the URL loads HTML but `/api/v1/*` returns 404, the Next.js `rewrites()` block is missing or malformed — see `next.config.ts`.

## Search (Meilisearch)

`docker-compose.yml` includes the `meilisearch` service (port 7700) and a `meilisearch-test` profile (port 7701).

```bash
docker compose up -d meilisearch
curl http://localhost:7700/health         # → {"status":"available"}
```

After `alembic upgrade head` + seed, populate the search indexes:

```bash
cd backend/app
uv run python -m app.search.reindex --all
```

Useful flags: `--products` / `--stores` / `--search-terms` rebuild a single index; `--products --swap-on-finish` does a zero-downtime alias swap; `--products --since 1h` is incremental.

For tests, the test instance lives behind `--profile test`:

```bash
docker compose --profile test up -d meilisearch-test
```

Dashboard: `http://localhost:7700`. Master key: `MEILI_MASTER_KEY` (default `dev-master-key-change-me`).
