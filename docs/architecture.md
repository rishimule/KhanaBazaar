# Architecture Overview

KhanaBazaar is a multi-vendor hyperlocal e-commerce platform for the Indian
market. Admins curate a master catalog; sellers run one store per account
spanning multiple services (Grocery, Food, Pharmacy); customers browse
per-store inventory and pay over UPI.

This document explains *why* the stack looks the way it does and *how* the
pieces fit together. Setup commands live in [CLAUDE.md](../CLAUDE.md) and
[docs/local_setup.md](local_setup.md).

## Tech Stack

| Layer            | Technology                                            | Why |
|------------------|-------------------------------------------------------|-----|
| API              | FastAPI 0.135+ (Python 3.12), Uvicorn ASGI            | Async-native, OpenAPI-first, fast dev loop |
| ORM / Migrations | SQLModel 0.0.37 + Alembic, asyncpg driver             | Pydantic + SQLAlchemy in one type; first-class async |
| Database         | PostgreSQL 15                                         | Relational integrity for inventory + orders; matches Render plan |
| Cache / Broker   | Redis 7 (+ Celery 5.6)                                | OTP rate limits, Celery broker, future caching |
| Auth             | Self-hosted email-OTP + JWT (PyJWT HS256)             | No vendor lock-in, no passwords, low onboarding friction in India |
| Email            | `EMAIL_PROVIDER=console` (dev) / `resend` (prod)      | Direct httpx POST to Resend REST API; no SDK dependency |
| Frontend         | Next.js 16.1 (App Router), React 19.2, TypeScript 5   | RSC + streaming, single deploy unit, strong DX |
| Styling          | CSS Modules + design tokens                           | Scoped styles, zero runtime, no Tailwind tax |
| PWA              | `frontend/public/sw.js` + `manifest.json`             | Installable on low-end Android, offline shell |
| Tooling          | `uv` (backend), `npm` (frontend), Ruff, Mypy strict, ESLint 9 | Fast, reproducible, strict by default |
| Testing          | Pytest + pytest-asyncio against real Postgres (`khanabazaar_test`) | Realism over speed; matches prod async stack |
| Deploy           | Render.com Blueprint (`render.yaml`)                  | One file provisions DB, Redis, API, worker, web |

## System Topology

Four runtime services in production, all in Render Singapore region:

```
                     +----------------------------+
   browser --------> |  Next.js (khanabazaar-web) |  (SSR + PWA shell)
                     +-------------+--------------+
                                   | HTTPS, NEXT_PUBLIC_API_URL
                                   v
                     +----------------------------+
                     |  FastAPI (khanabazaar-api) | --- /health, /api/v1/*
                     +--+-----------+-------------+
            asyncpg     |           | redis-py
                        v           v
              +-------------+  +----------------------+
              | Postgres 15 |  |  Redis (keyvalue)    |
              | khanabazaar |  |  OTPs, rate limits,  |
              +------^------+  |  Celery broker       |
                     |         +----------+-----------+
                     |                    | broker
                     |                    v
                     |       +-------------------------------+
                     +------ | Celery worker (khana...-worker)|
                             | async email send, future jobs |
                             +-------------------------------+
```

Local dev mirrors this: `docker-compose up` provisions Postgres and Redis;
`uvicorn` and `next dev` run on the host.

## Request & Auth Flow

1. User submits email at `/api/v1/auth/otp/request`. Backend stores a
   peppered hash of the OTP in Redis with TTL (`OTP_TTL_SECONDS`, default
   600s) and rate-limits per email and per hour (`OTP_MAX_*`).
2. Email is sent via `EMAIL_PROVIDER`: `console` logs to stdout in dev;
   `resend` POSTs directly to `api.resend.com` over httpx (no SDK).
3. `/auth/otp/verify` returns a JWT (HS256, `JWT_SECRET`, 24h expiry).
4. Frontend stores the JWT and sends `Authorization: Bearer <jwt>`.
5. `app.core.security` decodes the token, loads the `User`, and exposes
   role-checked dependencies to routers (`UserRole.Admin/Seller/Customer`).
6. CORS allowlists `localhost:3000` / `127.0.0.1:3000` in dev; prod origin
   is supplied via `FRONTEND_ORIGIN`.

API root is `/api/v1` (see `core/config.py`). Routers mounted in
`api/__init__.py`: `auth`, `catalog`, `stores`, `tasks`, `sellers`,
`customers`, `carts`, `orders`, `meta`.

## Data Model

Three concerns: identity, catalog (admin-curated), commerce (seller-run).

```
User --+-- SellerProfile -- Store -- StoreInventory --> MasterProduct
       |                                                      ^
       +-- CustomerProfile -- Address                          |
                                                               |
Service -- Category -- Subcategory -------------------- MasterProduct
   |          |             |                                  |
   +ServTrans +CatTrans     +SubcatTrans            MasterProductTranslation
       |
       +-- (en, hi, mr, gu, pa)  five seeded Languages
```

Key invariants:

- **One seller, one store** — enforced by `UniqueConstraint("seller_profile_id")`
  on `Store`. A single store spans many services.
- **Service to Category to Subcategory to MasterProduct** is the canonical
  taxonomy; sellers cannot create master products, only stock them.
- **Inventory per-store, per-product** — `StoreInventory` carries `price`,
  `stock`, `is_available`. Two stores can list the same `MasterProduct` at
  different prices.
- **Catalog is multilingual** via `*Translation` tables keyed by
  `language_code`. `User.preferred_language` drives default translation.
- **All tables inherit `BaseSchema`** — `id`, `created_at`, `updated_at`
  with timezone-aware UTC timestamps.

## Background Jobs

Celery worker (`app.core.celery_app` + `app.worker`) consumes jobs off
Redis. Current scope is small (e.g. async email dispatch, OTP send retries);
the worker exists primarily so future order-lifecycle and notification work
has a home without re-platforming.

## Testing Strategy

Backend tests run against a real `khanabazaar_test` Postgres database — not
SQLite — because production behavior depends on asyncpg, JSONB, and
Postgres constraint semantics. Auth dependencies are overridden via
`app.dependency_overrides` (see `tests/conftest.py`). There is no frontend
test suite yet; type checking and ESLint are the safety net.

## Deployment

`render.yaml` is the single source of truth for cloud infra:

| Resource              | Type     | Purpose                              |
|-----------------------|----------|--------------------------------------|
| `khanabazaar-db`      | postgres | Postgres 15, basic-256mb plan        |
| `khanabazaar-redis`   | keyvalue | Cache + Celery broker, `noeviction`  |
| `khanabazaar-api`     | web      | FastAPI; `./build.sh`, `./predeploy.sh` (migrations) |
| `khanabazaar-worker`  | worker   | Celery worker, concurrency 2         |
| `khanabazaar-web`     | web      | Next.js, `npm ci && npm run build`   |

Secrets `JWT_SECRET` and `OTP_PEPPER` use `generateValue: true`. Resend
keys and `FRONTEND_ORIGIN` are `sync: false` — set manually in the
dashboard. `NEXT_PUBLIC_API_URL` is inlined at build time, so the web
service must be re-deployed after changing it.

## Non-obvious Decisions

- **No Firebase, no third-party auth.** Self-hosted OTP keeps user data in
  one Postgres and avoids per-MAU pricing. JWT is HS256 with a single
  shared secret — fine for one API; revisit if a second service joins.
- **No active password column.** `User.hashed_password` exists but is
  unused; OTP is the only verification path.
- **No Tailwind.** CSS Modules + design tokens (`frontend/src/styles/`)
  avoid build-time class generation and keep payload small for
  low-bandwidth users.
- **Resend over httpx, not the SDK.** One fewer dep, one fewer version
  pin, trivial JSON POST.
- **Postgres for everything.** No separate search engine yet; full-text
  needs are met by `ILIKE` and indexes. Reassess at scale.
- **Render, not Azure.** `render.yaml` Blueprint provisions the entire
  stack from one file; cheaper to operate at current size.

## Further Reading

- [User & Data Flows](flows.md) — guest cart, auth merge, checkout, fulfillment
- [Local Setup](local_setup.md) — Docker, backend, frontend walkthrough
- [Development Guide](development_guide.md) — env vars, Alembic, troubleshooting
- [Seller Signup](seller_signup.md) — onboarding wizard, admin approval
- [Roadmap](../TODO.md) — phase tracker
