<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Khana Bazaar

Multi-vendor hyperlocal e-commerce platform for the Indian market — Instacart-style, with admin-curated catalogs, seller-managed local inventory, and UPI checkout.

- **Admins** maintain a master product catalog (services, categories, subcategories, master products) — multi-lingual (en, hi, mr, gu, pa).
- **Sellers** register, get admin-approved, run **one store** with **multiple services** (Grocery, Food, Pharmacy, …), and manage per-store inventory + pricing.
- **Customers** shop one store at a time, pay via UPI, and check out per-store.

Auth is **email-OTP + JWT** — no passwords, no Firebase. Seller signup adds a phone-OTP step (Twilio in prod, console in dev).

Search is powered by **Meilisearch** (products / stores / search terms indexes, kept in sync via SQLAlchemy `after_commit` hooks → Celery tasks). Delivery serviceability + distance ranking run on **PostGIS** (`ST_DWithin`, `ST_Distance`) with Google Maps Platform proxied server-side via `/api/v1/geo/*` (key never reaches the browser).

## Tech Stack

| Layer | Stack |
|------|------|
| Backend | FastAPI 0.135, Python 3.12, Uvicorn, SQLModel + Alembic, asyncpg |
| Database | PostgreSQL 15 + PostGIS 3.4 (`postgis/postgis:15-3.4` locally) |
| Cache / Broker | Redis 7, Celery 5.6 |
| Search | Meilisearch v1.11 (Docker locally; Azure Container App in prod) |
| Geo | Google Maps Platform (server-side proxy via `/api/v1/geo/*`) |
| Auth | Self-hosted email-OTP + JWT (PyJWT HS256) |
| Email | `console` (dev) / `resend` (prod, raw httpx) |
| SMS | `console` (dev) / `twilio` (prod, raw httpx) — used by seller phone OTP |
| Frontend | Next.js 16.1 (App Router), React 19.2, TypeScript 5, CSS Modules + design tokens |
| PWA | `frontend/public/sw.js` + `manifest.json` |
| Tooling | `uv` (backend), `npm` (frontend), Ruff + Mypy, ESLint 9, Pytest |
| Deploy | Microsoft Azure (Container Apps + Postgres Flexible Server + Cache for Redis), provisioned via Bicep + `azd` |

## Repo Layout

```
backend/app/             FastAPI service (run from here)
  src/app/api/           Routers — auth, catalog, catalog_admin, stores, sellers, customers,
                          carts, orders, search, geo, admin_actions, tasks, meta
  src/app/core/          config, security, otp, email, sms, redis, celery_app, rate_limit,
                          google_maps, locale, indian_states
  src/app/models/        SQLModel tables (base, address, catalog, profile, commerce, store, seller)
  src/app/services/      Business logic (checkout, orders, inventory, profiles, admin_audit, …)
  src/app/search/        Meilisearch client, indexes, sync hooks, Celery sync tasks, reindex CLI
  src/app/schemas/       Pydantic request/response models
  src/app/utils/         address helpers, digipin, indian_states
  src/app/worker.py      Celery tasks (OTP/email dispatch, order emails, search sync, admin notifs)
  migrations/            Alembic versions
  tests/                 Pytest suite (uses real Postgres `khanabazaar_test` + Meili test container)
  scripts/               seed_database.py, seed_seller_applications.py, bake_mumbai_seed.py
frontend/src/
  app/                   Next.js App Router (stores, cart, checkout, account, seller, admin)
  components/            Navbar, Footer, DashboardLayout, DataTable, Modal, ProductCard,
                          AddressFields, MapPicker, DeliveryLocationPicker, orders/*
  lib/                   api, AuthContext, CartContext, DeliveryLocationContext, orders,
                          format-address, localCart, remoteCart
  styles/                design-tokens.css, globals.css
  public/                icons/, manifest.json, sw.js
docs/                    architecture, flows, local_setup, development_guide, azure_deployment,
                          seller_signup, google_maps_setup, price_comparison
scripts/                 dev.sh, reset_local_state.sh, log_viewer.py
infra/                   Bicep modules + azure.yaml (azd)
```

## Prerequisites

- Docker + Docker Compose
- Python 3.12 + [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ + npm

## For non-engineer teammates

If you are not a developer and have never installed Docker / Node / Python before, follow [the teammate onboarding guide](docs/teammate-guide/README.md) instead. It walks Windows users through every install step from scratch and ends with a working demo.

## Local Setup

### 1. Copy env files

```bash
cp backend/app/.env.example backend/app/.env
cp frontend/.env.example   frontend/.env.local
```

Generate real secrets for `JWT_SECRET` and `OTP_PEPPER`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"   # JWT_SECRET
python -c "import secrets; print(secrets.token_hex(16))"   # OTP_PEPPER
```

`EMAIL_PROVIDER=console` prints OTP codes to backend logs — fine for dev.

### 2. Install deps + run migrations + seed

```bash
# Postgres + Redis + Meilisearch
docker compose up -d postgres redis meilisearch

# Backend
cd backend/app
uv sync
uv run alembic upgrade head
uv run python scripts/seed_database.py
uv run python -m app.search.reindex --all     # populate Meili indexes (products, stores, search_terms)
cd ../..

# Frontend
cd frontend
npm install
cd ..
```

### 3. Start everything (one command)

```bash
./scripts/dev.sh start
```

Brings up Postgres + Redis + Meilisearch (Docker), backend (Uvicorn :8000), Celery worker, frontend (Next.js :3000), and a lightweight SSE log viewer on :8001 streaming `.dev/logs/*.log`. Logs land in `.dev/logs/`.

```bash
./scripts/dev.sh status              # pids + docker (incl. ngrok URL when tunnel up)
./scripts/dev.sh logs backend        # tail single log (also: celery, frontend, ngrok, log_viewer)
./scripts/dev.sh stop                # stop app procs (incl. tunnel + log viewer)
./scripts/dev.sh stop --all          # also stop Postgres + Redis + Meilisearch
./scripts/dev.sh restart
./scripts/dev.sh start --tunnel      # also start ngrok forwarding :3000 (mobile testing)
./scripts/dev.sh tunnel-url          # print current public URL
```

For real-device testing on a phone (over mobile data, not just same-wifi), use `start --tunnel`. ngrok forwards only `:3000`; backend stays loopback-only and Next.js proxies `/api/v1/*` server-side. See [`docs/local_setup.md`](docs/local_setup.md#6a-mobile-testing-via-ngrok-optional) for details.

### Run things manually (alternative)

```bash
# from backend/app
uv run uvicorn app.main:app --reload                          # API on :8000
uv run celery -A app.core.celery_app worker --loglevel=info   # worker
# from frontend
npm run dev                                                   # UI on :3000
```

API docs: http://localhost:8000/docs · Frontend: http://localhost:3000 · Log viewer: http://localhost:8001 · All API routes prefixed `/api/v1`.

## API Surface

All routes mounted in `app/api/__init__.py` under `/api/v1`:

| Prefix | Module | Purpose |
|--------|--------|---------|
| `/auth` | `auth.py` | Email + phone OTP request/verify, seller signup token chain, login, logout, me |
| `/catalog` | `catalog.py` | Public reads — languages, services, categories, subcategories, master products |
| `/catalog` (admin) | `catalog_admin.py` | Admin writes — create/update master catalog entries |
| `/stores` | `stores.py` | Store list/detail (PostGIS distance + radius filter), inventory CRUD |
| `/sellers` | `sellers.py` | Seller register, profile, services, applications, status |
| `/customers` | `customers.py` | Customer profile + addresses |
| `/carts` | `carts.py` | Per-(store, service) sub-baskets, server-side sync, single-sub-basket clear |
| `/orders` | `orders.py` | Create, list (optional `?service_id=`), detail, status transitions, cancel |
| `/search` | `search.py` | `/suggest` (dropdown), `/products` (results), `/products/{id}/stores` (compare), `/stores`, `/click` |
| `/geo` | `geo.py` | Server-side Google Maps proxy: autocomplete, place, reverse, serviceability |
| `/admin` | `admin_actions.py` | Per-seller supervisor hub, activity log, order force-rewind/refund, address override |
| `/tasks` | `tasks.py` | Celery test endpoint |
| `/meta` | `meta.py` | Health, languages |

Public: catalog reads, store reads, search, geo, health. Seller-only: register, profile/services updates, applications. Admin-only: catalog writes, seller approval, per-seller supervisor actions.

## Test Accounts (after seeding)

Login is email-OTP. With `EMAIL_PROVIDER=console` the OTP is printed to the backend log — `./scripts/dev.sh logs backend` (or stdout if running uvicorn directly).

| Role | Email |
|------|------|
| Admin | `admin@khanabazaar.dev` |
| Seller (Sharma Store) | `seller@khanabazaar.dev` |
| Seller (Krishna Store) | `seller2@khanabazaar.dev` |
| Seller (Balaji Store) | `seller3@khanabazaar.dev` |
| Customer | `customer@khanabazaar.dev` |

Sellers `seller4@…` through `seller9@…` also exist. The login page exposes quick-login buttons for these dev accounts.

## Common Commands

### Backend (`cd backend/app`)

```bash
uv run alembic revision --autogenerate -m "msg"   # new migration
uv run alembic upgrade head                       # apply
uv run pytest -v                                  # test suite (needs khanabazaar_test DB + meili-test :7701)
uv run ruff check .                               # lint
uv run mypy .                                     # type-check
uv run python -m app.search.reindex --all         # rebuild all Meilisearch indexes
uv run python -m app.search.reindex --products    # single-index variants also: --stores, --search-terms
```

### Frontend (`cd frontend`)

```bash
npm run dev
npm run build
npm run lint
```

## Environment Variables

### Backend — `backend/app/.env`

| Var | Required | Default |
|-----|----------|---------|
| `DATABASE_URL` | yes | `postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar` |
| `REDIS_URL` | yes | `redis://localhost:6379/0` |
| `JWT_SECRET` | yes | — |
| `OTP_PEPPER` | yes | — |
| `ENVIRONMENT` | no | `development` |
| `JWT_EXPIRES_HOURS` | no | `24` |
| `OTP_TTL_SECONDS` | no | `600` |
| `OTP_MAX_ATTEMPTS` | no | `5` |
| `OTP_RESEND_COOLDOWN` | no | `60` |
| `OTP_MAX_PER_HOUR` | no | `5` |
| `EMAIL_PROVIDER` | no | `console` (`resend` for prod) |
| `RESEND_API_KEY` / `RESEND_FROM_EMAIL` | only if `resend` | — |
| `SMS_PROVIDER` | no | `console` (`twilio` for prod) — drives seller phone OTP |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | only if `twilio` | — |
| `FRONTEND_ORIGIN` | no | `http://localhost:3000,http://127.0.0.1:3000` (comma-separated CORS allow-list) |
| `GOOGLE_MAPS_SERVER_API_KEY` | for geo features | — (IP-restricted in GCP; powers `/api/v1/geo/*`) |
| `GOOGLE_MAPS_BROWSER_API_KEY` | for geo features | — (referrer-restricted; exposed to FE as `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`) |
| `GEO_RATE_LIMIT_PER_MIN` | no | `30` |
| `GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS` | no | `60` |
| `GEO_REVERSE_CACHE_TTL_SECONDS` | no | `86400` |
| `MEILI_URL` | no | `http://localhost:7700` |
| `MEILI_MASTER_KEY` | no | `dev-master-key-change-me` (dev only — change for prod) |
| `SEARCH_RATE_LIMIT_SUGGEST_PER_MIN` | no | `60` |
| `SEARCH_RATE_LIMIT_PRODUCTS_PER_MIN` | no | `30` |
| `SEARCH_SUGGEST_CACHE_TTL_SECONDS` | no | `60` |
| `SEARCH_SERVICEABLE_GRID_TTL_SECONDS` | no | `60` |

### Frontend — `frontend/.env.local`

| Var | Default |
|-----|---------|
| `NEXT_PUBLIC_API_URL` | `""` (empty — Next.js `rewrites()` proxies `/api/v1/*` to the backend) |
| `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY` | — (referrer-restricted key for the in-browser map picker / autocomplete; see `docs/google_maps_setup.md`) |

## Deployment

Microsoft Azure — Container Apps (api, worker, web) + Postgres Flexible Server + Cache for Redis, fronted by Azure Front Door. Infra is Bicep + `azd up`; CI/CD is GitHub Actions with OIDC. See [`docs/azure_deployment.md`](docs/azure_deployment.md).

## Documentation

- [Architecture](docs/architecture.md) — topology, stack rationale, data model
- [Flows](docs/flows.md) — guest cart, OTP auth, cart sync, per-store checkout, seller signup
- [Local setup](docs/local_setup.md) — Docker + backend + frontend setup, ngrok mobile testing
- [Development guide](docs/development_guide.md) — Alembic, OTP/JWT, Celery, search, geo, testing
- [Seller signup](docs/seller_signup.md) — wizard, 4-OTP email+phone chain, admin approval
- [Google Maps setup](docs/google_maps_setup.md) — provisioning server + browser API keys, restrictions
- [Price comparison](docs/price_comparison.md) — cross-store product comparison UX
- [Azure deployment](docs/azure_deployment.md) — Container Apps, Postgres Flexible Server, Cache for Redis, Bicep + `azd`
- [Phase tracker](TODO.md)

## Contributing

- Branch off `main`: `feat/`, `fix/`, `chore/`, `docs/`, `refactor/`, `test/`.
- Conventional Commits — `<type>(<scope>): <summary>`, ≤72 chars, no trailing period.
- PRs target `main`, must pass CI (lint + types + tests), merged via merge-commit (`gh pr merge --merge`).
- Never commit `.env` / secrets; never `git push --force` on shared branches.

## Copyright

Copyright © 2026 Rishi Mule. All rights reserved.

This source code and all associated assets are the proprietary and confidential property of Rishi Mule. No part of this repository — including but not limited to the source code, design, documentation, schemas, and configuration — may be used, copied, reproduced, modified, merged, published, distributed, sublicensed, sold, or otherwise exploited, in whole or in part, by any person or entity, for any purpose (commercial or non-commercial), without the **prior written and explicit permission of Rishi Mule**.

Unauthorized use, reproduction, or distribution is strictly prohibited and may result in civil and criminal liability under applicable copyright and intellectual property laws.

For licensing or permission inquiries, contact: **mulerishi1234@gmail.com**.
