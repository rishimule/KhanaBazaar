<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
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
| Database         | PostgreSQL 15 + PostGIS 3.4                           | Relational integrity for inventory + orders; PostGIS powers distance sort + per-store delivery radius (`ST_DWithin` / `ST_Distance` on a `geography(Point, 4326)` GENERATED column with GiST index); matches Cloud SQL for PostgreSQL target |
| Cache / Broker   | Redis 7 (+ Celery 5.6)                                | OTP rate limits, Celery broker, suggest cache + serviceable-store grid |
| Search           | Meilisearch v1.11 (Docker locally; Cloud Run in prod) | Typo-tolerant multi-language autocomplete with synonyms; ~30 ms p95 query; kept in sync via SQLAlchemy `after_commit` hooks → Celery |
| Auth             | Self-hosted email-OTP + JWT (PyJWT HS256)             | No vendor lock-in, no passwords, low onboarding friction in India |
| Email            | `EMAIL_PROVIDER=console` (dev) / `resend` (prod)      | Direct httpx POST to Resend REST API; no SDK dependency |
| Frontend         | Next.js 16.1 (App Router), React 19.2, TypeScript 5   | RSC + streaming, single deploy unit, strong DX |
| Styling          | CSS Modules + design tokens                           | Scoped styles, zero runtime, no Tailwind tax |
| PWA              | `frontend/public/sw.js` + `manifest.json`             | Installable on low-end Android, offline shell |
| Tooling          | `uv` (backend), `npm` (frontend), Ruff, Mypy strict, ESLint 9 | Fast, reproducible, strict by default |
| Testing          | Pytest + pytest-asyncio against real Postgres (`khanabazaar_test`) | Realism over speed; matches prod async stack |
| Deploy           | Google Cloud Platform (Cloud Run + Cloud SQL for PostgreSQL + Memorystore for Redis), `asia-south1` (Mumbai) | Managed serverless, Cloud Run scales api/web to zero, no VM/kubelet babysitting |

## System Topology

Five Cloud Run services + two managed data services in production, all in
GCP **Mumbai** (`asia-south1`):

```
                                 ┌──────────────────────┐
       browser ────────────────► │  Cloud Run domain map│  TLS (managed certs),
                                 │  khanabazaar.in      │  custom hostname
                                 └────────┬─────────────┘
                                          │
                ┌─────────────────────────┴──────────────────────────┐
                ▼                                                    ▼
   +----------------------------+                       +----------------------------+
   |  Cloud Run: web            |                       |  Cloud Run: api            |
   |  Next.js (khanabazaar-web) | ── HTTPS, JWT ──────► |  FastAPI (khanabazaar-api) | --- /health, /api/v1/*
   |  min=0, public ingress     |                       |  min=0, public ingress     |
   +-------------+--------------+                       +--+-----------+-------------+
                                                  asyncpg    |           | redis-py
                                                  (priv IP)  v           v
                                                  +-------------+  +----------------------+
                                                  | Cloud SQL   |  |  Memorystore for     |
                                                  | Postgres 15 |  |  Redis (Basic 1 GiB) |
                                                  | + PostGIS   |  |  OTPs, rate limits,  |
                                                  | private IP  |  |  Celery broker       |
                                                  +------^------+  +----------+-----------+
                                                         |                    | broker
                                                         |        ┌───────────┴─────────────┐
                                                         |        ▼                          ▼
                                                         |  +----------------+   +------------------+
                                                         +- | Cloud Run:     |   | Cloud Run: beat  |
                                                            | worker         |   | Celery beat,     |
                                                            | Celery worker  |   | min=max=1        |
                                                            | min=1 (CPU     |   | (CPU always-on)  |
                                                            | always-on)     |   +---------+--------+
                                                            +-------+--------+             │
                                                                    │ HTTP                 │
                                                                    ▼                      │
                                                            +----------------------------+ │
                                                            | Cloud Run: meilisearch     | │
                                                            | products / stores /        |◄┘
                                                            | search_terms indexes       |
                                                            | internal ingress, GCS Fuse |
                                                            | → /meili_data, min=max=1    |
                                                            +----------------------------+
```

Beat runs as its own Cloud Run service (`khanabazaar-beat`, `min=max=1`, CPU
always-allocated) — pinned to a single instance so scheduled tasks fire
exactly once. Worker and beat keep CPU always-allocated because Cloud Run
otherwise throttles CPU outside request handling, which would stall the
Celery event loop.

Local dev mirrors this: `docker-compose up` provisions Postgres, Redis, and Meilisearch;
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
6. CORS is fully driven by `FRONTEND_ORIGIN` (comma-separated). Default
   in `core/config.py` is `http://localhost:3000,http://127.0.0.1:3000`
   for dev; prod sets it to the public frontend URLs via the Cloud Run
   service env (`--set-env-vars FRONTEND_ORIGIN=...`).

API root is `/api/v1` (see `core/config.py`). Routers mounted in
`api/__init__.py`: `auth`, `catalog`, `catalog_admin`, `stores`, `sellers`,
`customers`, `carts`, `orders`, `search`, `geo`, `admin_actions`, `tasks`,
`meta`.

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
- **Geo on every `Address`** — `latitude`, `longitude` columns plus a Postgres
  GENERATED `geo geography(Point, 4326)` column with a GiST index, computed
  automatically from lat/lng. `digipin` (India Post 10-char code) is derived
  in Python by `address_from_payload`. `Store` carries `delivery_radius_km`
  + `pin_confirmed`. Distance filter via `ST_DWithin`, sort via `ST_Distance`.
- **Google Maps proxied** — `/api/v1/geo/{autocomplete,place,reverse,serviceability}`
  hides the server API key, caches in Redis, rate-limits per IP.

## Background Jobs

Celery worker (`app.core.celery_app` + `app.worker`) consumes jobs off
Redis. Live scope:

- **OTP email dispatch** — `send_otp_email_async` (login + seller email
  verification).
- **Order-lifecycle emails** — placed / status-change notifications via
  `app.services.order_emails`.
- **Admin order-action emails** — `send_admin_order_action_email` fires
  when an admin force-cancels, refunds, or transitions a seller's order
  (loops the seller in on the supervisor activity).
- **Seller onboarding emails** — `send_seller_approved_async` and
  `send_seller_rejected_async` close the admin-approval loop (the
  `/seller/signup/pending` status poll is now a fallback, not the only
  signal).
- **Customer support forwarding** — `send_support_email` ships
  `/customers/me/support` messages to `SUPPORT_EMAIL`.
- **Meilisearch sync** — SQLAlchemy `after_commit` listeners → Celery
  tasks (`app.search.tasks`); see the search section below.
- **One-shot geocode backfill** — `backfill_store_addresses_geocode`
  forward-geocodes legacy seller/store addresses (idempotent, manually
  triggered, skips low-confidence Google matches).

Admin actions also write to `admin_action_log` **in the same DB
transaction** as the mutation (see `app.services.admin_audit`) — not a
background job, but the rollback-safe audit trail that the admin
supervisor UI reads.

Celery beat runs the scheduled side: `search.reconcile_index` hourly per
kind (`product`, `store`) plus a daily deep pass, `search.verify_drift`
nightly at 04:30 UTC (legacy safety net), `search.rebuild_search_terms`
nightly at 03:15 UTC, and `search.prune_query_log` daily at 04:00 UTC.
In prod, beat lives in its own Cloud Run service (see topology above).
Failed Meilisearch sync attempts land in Redis sets
`search:dlq:{product,store}` and are drained by the reconciler.

## Testing Strategy

Backend tests run against a real `khanabazaar_test` Postgres database — not
SQLite — because production behavior depends on asyncpg, JSONB, and
Postgres constraint semantics. Auth dependencies are overridden via
`app.dependency_overrides` (see `tests/conftest.py`). There is no frontend
test suite yet; type checking and ESLint are the safety net.

## Deployment

Production runs on **Google Cloud Platform** in `asia-south1` (Mumbai),
managed serverless throughout — Cloud Run for every app tier, Cloud SQL +
Memorystore for data. Infra-as-code lands in `infra/` (Terraform) +
`deploy/gcp/` (Cloud Run manifests); nothing is committed there yet
(Phase 5). See [`gcp_deployment.md`](gcp_deployment.md) for the full
provisioning runbook, cost model, and deploy mechanics.

| Resource (name)            | Service                                  | Purpose                                       |
|----------------------------|------------------------------------------|-----------------------------------------------|
| `khanabazaar-pg`           | Cloud SQL for PostgreSQL (`db-f1-micro`) | Primary data store, private IP only, PostGIS extension |
| `khanabazaar-redis`        | Memorystore for Redis (Basic 1 GiB)      | Cache + Celery broker, `noeviction`, VPC-internal |
| `khanabazaar-api`          | Cloud Run (HTTP)                         | FastAPI; image from Artifact Registry, public ingress, min=0 |
| `khanabazaar-worker`       | Cloud Run (no ingress, CPU always-on)    | Celery worker, min=1                          |
| `khanabazaar-beat`         | Cloud Run (no ingress, CPU always-on)    | Celery beat scheduler, min=max=1              |
| `khanabazaar-meili`        | Cloud Run (internal ingress)             | Meilisearch v1.11, GCS Fuse mount for `/meili_data`, min=max=1 |
| `khanabazaar-web`          | Cloud Run (HTTP)                         | Next.js (`output: "standalone"`), min=0       |
| `khanabazaar-migrate`      | Cloud Run Job                            | One-shot `alembic upgrade head` per deploy    |
| `khanabazaar` (AR repo)    | Artifact Registry (Docker)               | Image hosting, pulled via service account     |
| Secret Manager             | Secret Manager                           | Secrets — JWT, OTP pepper, Resend, Twilio, DB URL, Meili master key, Google Maps keys |
| domain mapping             | Cloud Run domain mapping (managed certs) | TLS + custom domain (`khanabazaar.in`)        |
| Cloud Logging + Monitoring | Cloud Logging + Cloud Monitoring         | Structured logs, metrics, traces (free tier covers MVP) |

`JWT_SECRET` and `OTP_PEPPER` live in **Secret Manager** and are mounted on
each Cloud Run service via `--set-secrets ENV_NAME=secret:version` — Cloud
Run injects them as env vars at start. Resend, Twilio, and Google Maps keys
are Secret Manager secrets too, populated by the GitHub Actions workflow on
first deploy (auth via Workload Identity Federation — no long-lived service
account keys). `FRONTEND_ORIGIN` is a plain env var (not secret) — backend
reads it via `Settings.cors_origins`. `NEXT_PUBLIC_API_URL` is inlined at
build time, so the `web` image must be rebuilt for any URL change.

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
- **PostGIS over a custom haversine.** GIS-native indexes scale to 10k+
  stores without a full scan, and the `geography` type future-proofs the
  schema for polygon delivery zones. The `geo` column is a STORED GENERATED
  column, so it never drifts from `latitude`/`longitude` even when an
  Alembic data migration writes raw SQL.
- **DIGIPIN derived in Python, not the DB.** India Post's algorithm is
  trivial to implement and keeps the encoder testable + portable. Storing
  it lets future couriers index addresses by the 10-char grid code without
  a re-derivation pass.
- **Google Maps proxied through the backend.** Hides the server API key
  (the browser key is referrer-restricted but only powers the map render),
  enables Redis caching to cap upstream cost, and lets us swap providers
  later (MapmyIndia, OSM) without touching the frontend.
- **GCP, all managed serverless.** Cloud Run + managed Cloud SQL + managed
  Memorystore. No VMs, no GKE, no hand-managed certs — Cloud Run domain
  mapping does managed TLS, and Workload Identity Federation removes every
  static credential except the GitHub OIDC trust. api/web scale to zero;
  worker/beat/meili stay warm at min=1.

## Further Reading

- [User & Data Flows](flows.md) — guest cart, auth merge, checkout, fulfillment
- [Local Setup](local_setup.md) — Docker, backend, frontend walkthrough
- [Development Guide](development_guide.md) — env vars, Alembic, troubleshooting
- [GCP Deployment](gcp_deployment.md) — Cloud Run, Cloud SQL, Memorystore, deploy runbook
- [Seller Signup](seller_signup.md) — onboarding wizard, admin approval
- [Roadmap](../TODO.md) — phase tracker
