# Khana Bazaar

Multi-vendor hyperlocal e-commerce platform for the Indian market (Instacart-like model).
Admins curate a master product catalog. Sellers register, get admin-approved, run **one store** with **multiple services** (Grocery, Food, Pharmacy, etc.) and manage local inventory/pricing. Customers shop per-store and pay via UPI.

## Subagent routing (gemini-worker)

This project has a `gemini-worker` subagent that wraps the Gemini CLI. It exists to preserve Claude context for planning, writing code, and reviewing diffs.

**Delegate to `gemini-worker` before:**
- Reading more than 3 files to answer a question
- Any codebase-wide search ("find every place we…", "list all usages of…")
- Summarizing any file longer than ~500 lines
- Reading generated code, large logs, large JSON/CSV, or vendored dependencies
- Answering "does this repo already have X?" questions

**Do NOT delegate (do it yourself):**
- Editing, creating, or deleting files
- Running tests, linters, or build commands
- Git operations
- Brainstorming, plan-writing, or spec refinement — plan quality depends on you reading the code directly
- Reviewing a diff against a plan
- Small reads (1–3 specific files you already know you need)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI 0.135+ (Python 3.12), Uvicorn ASGI |
| ORM / Migrations | SQLModel 0.0.37+ + Alembic (asyncpg driver) |
| Database | PostgreSQL 15 |
| Cache / Broker | Redis 7 (Celery 5.6+ for background tasks) |
| Auth | Self-hosted email-OTP + JWT (PyJWT HS256). **No Firebase, no passwords.** |
| Email | `EMAIL_PROVIDER=console` (dev) or `resend` (prod, raw httpx call — no SDK) |
| Config | Pydantic-Settings (`.env` files) |
| Frontend | Next.js 16.1 (App Router), React 19.2, TypeScript 5 |
| Frontend styling | CSS Modules + design tokens in `frontend/src/styles/design-tokens.css` (no Tailwind) |
| PWA | `frontend/public/sw.js` + `manifest.json` (registered in `app/layout.tsx`) |
| Package mgmt | `uv` (backend), `npm` (frontend) |
| Linting/Types | Ruff + Mypy (backend), ESLint 9 + TypeScript (frontend) |
| Testing | Pytest + pytest-asyncio (backend). **No frontend tests.** |
| Deployment | Render.com Blueprint (`render.yaml`, `docs/render_deployment.md`) |

## Project Structure

```
backend/app/                          # FastAPI app (run commands from here)
  src/app/
    main.py                           # Uvicorn entrypoint
    __init__.py                       # FastAPI app instance, CORS, route mounting
    api/                              # Routers (see API Surface below)
    core/                             # config, security, otp, email, redis, celery_app, rate_limit, indian_states
    db/                               # async session factory, seed scripts
    models/                           # SQLModel tables (base, address, catalog, profile, commerce, store, seller)
    services/                         # Business logic: checkout, orders, order_emails, seller_services, inventory, profiles
    schemas/                          # Pydantic request/response models
    utils/                            # address helpers, indian_states
    worker.py                         # Celery task definitions
  migrations/                         # Alembic versions
  tests/                              # Pytest integration tests (separate khanabazaar_test DB)
  pyproject.toml
frontend/
  src/
    app/                              # Next.js App Router
      stores/[id]/                    # Instacart-style service/category/subcategory layout
      cart/, checkout/[storeId]/      # Per-store checkout flow
      account/                        # Customer dashboard (orders, settings)
      seller/                         # Seller dashboard (signup, inventory, orders) — DashboardLayout
      admin/                          # Admin dashboard (categories, products, sellers, orders) — DashboardLayout
    components/                       # Navbar, Footer, DashboardLayout, DataTable, Modal, ProductCard, orders/*
    lib/                              # api, AuthContext, CartContext, cart, localCart, remoteCart, orders, format-address
    types/index.ts                    # TS interfaces mirroring backend models
    styles/                           # design-tokens.css, globals.css
  public/                             # icons/, manifest.json, sw.js
docs/                                 # architecture, flows, local_setup, development_guide, render_deployment, seller_signup
docker-compose.yml                    # Postgres + Redis
render.yaml                           # Render Blueprint
```

## Essential Commands

### Infrastructure
```bash
docker-compose up -d                                          # Postgres + Redis
```

### Backend (from `backend/app/`)
```bash
uv sync                                                       # Install deps
uv run alembic upgrade head                                   # Apply migrations
uv run alembic revision --autogenerate -m "description"       # Generate migration
uv run uvicorn app.main:app --reload                          # Dev server (port 8000)
uv run celery -A app.core.celery_app worker --loglevel=info   # Celery worker
uv run pytest -v                                              # Tests (needs khanabazaar_test DB)
uv run ruff check .                                           # Lint
uv run mypy .                                                 # Types
```

### Frontend (from `frontend/`)
```bash
npm install
npm run dev                                                   # Port 3000
npm run build
npm run lint
```

API docs: `http://localhost:8000/docs`. All routes prefixed `/api/v1` (`core/config.py:8`).

## RBAC Roles

Defined in `backend/app/src/app/models/base.py:8-11`: **Customer**, **Seller**, **Admin**.

Auth chain (`core/security.py`):
- `HTTPBearer` → `decode_access_token` → `get_current_user` (loads User by JWT `sub`)
- Role guards: `get_current_seller`, `get_current_admin`
- Public endpoints take only `Depends(get_db_session)` (no auth)

## API Surface

Mounted in `api/__init__.py`. All under `/api/v1`:

| Prefix | Module | Purpose |
|--------|--------|---------|
| `/auth` | `auth.py` | OTP request/verify, login, logout, me |
| `/catalog` | `catalog.py` | Languages, services, categories, subcategories, master products |
| `/stores` | `stores.py` | Store list/detail, inventory |
| `/sellers` | `sellers.py` | Seller register, profile, services, applications, status |
| `/customers` | `customers.py` | Customer profile, addresses |
| `/carts` | `carts.py` | Cart ops, server-side sync |
| `/orders` | `orders.py` | Create, list, detail, status |
| `/tasks` | `tasks.py` | Celery test endpoint |
| `/meta` | `meta.py` | Health, languages |

Public: catalog reads, store reads, health, languages.
Seller-only: register, profile/services updates, applications.
Admin-only: create categories/products, approve seller applications.

## Environment Variables

### Backend `backend/app/.env`
**Required**: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `OTP_PEPPER`
**Optional**:
- `ENVIRONMENT` (development/production)
- `EMAIL_PROVIDER` (`console` default | `resend`)
- `RESEND_API_KEY`, `RESEND_FROM_EMAIL` (only when `EMAIL_PROVIDER=resend`)
- `JWT_EXPIRES_HOURS` (default 24)
- `OTP_TTL_SECONDS`, `OTP_MAX_ATTEMPTS`, `OTP_RESEND_COOLDOWN`, `OTP_MAX_PER_HOUR`

### Frontend `frontend/.env.local`
- `NEXT_PUBLIC_API_URL` — backend base URL (default `http://localhost:8000`)

## Testing

`backend/app/tests/conftest.py`:
- **Real Postgres test DB** (`khanabazaar_test`) — not SQLite, not mocked. Drop+recreate tables per function.
- Pre-seeds 5 languages (en, hi, mr, gu, pa) before each test.
- Auth dependencies overridden via `app.dependency_overrides` (see `test_stores.py` for pattern).
- Celery runs **eager mode** in tests (inline execution, no worker needed).
- Order-email dispatchers patched to no-op to avoid connection-pool races.

No frontend tests configured.

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/src/app/main.py` | Uvicorn entry |
| `backend/app/src/app/__init__.py` | App factory, CORS (`localhost:3000`), router mount |
| `backend/app/src/app/core/config.py` | Pydantic Settings, `API_V1_STR="/api/v1"` |
| `backend/app/src/app/core/security.py` | JWT encode/decode, role guards |
| `backend/app/src/app/db/session.py` | Async session factory |
| `frontend/src/app/layout.tsx` | Root layout, mounts AuthProvider + CartProvider, registers PWA manifest |
| `frontend/src/lib/api.ts` | Typed fetch wrapper, `ApiError` class |
| `frontend/src/lib/AuthContext.tsx` | Auth state (token in `localStorage` key `kb_token`, OTP flow) |
| `frontend/src/lib/CartContext.tsx` | Cart state + localStorage persistence |
| `frontend/src/types/index.ts` | TS interfaces mirroring backend models |

## Non-obvious patterns / gotchas

**Multi-vendor model**: 1 Seller → 1 Store → many Services (Grocery, Food, Pharmacy, …). Each Service has Categories → Subcategories → MasterProducts. Inventory is per-product per-store.

**Catalog is multi-lingual**: `Service`, `Category`, `Subcategory`, `MasterProduct` all have `*Translation` tables keyed by `LanguageCode`. Pre-seeded languages: en, hi, mr, gu, pa.

**Auth is email-OTP + JWT only**: No passwords, no Firebase. Endpoints: `POST /api/v1/auth/otp/request`, `POST /api/v1/auth/otp/verify`. Seller signup uses 2-step variant — `/auth/seller/otp/verify` returns short-lived `email_token`, then `/auth/seller/register` consumes it. OTP stored in Redis (TTL 600s default), rate-limited 5/hour per IP, 60s resend cooldown. JWT issued on verify (`sub=user.id`, `role=user.role`, 24h TTL).

**Cart architecture (frontend)**:
- Guest carts: `localStorage` key `kb_carts` (JSON map `storeId → CartItem[]`)
- Guest session ID: `localStorage` key `kb_session_id` (UUID, generated once)
- Logged-in users sync to backend via `POST /api/v1/carts/sync`
- Per-store cart isolation — no cross-store bundling

**Per-store checkout** (`services/checkout.py`, `app/checkout/[storeId]/page.tsx`): customer picks delivery address + payment method per store. Inventory row-locked + validated, then Order + OrderItems + Payment + Delivery created atomically. `OrderStatus` enum: `pending → packed → dispatched → delivered` plus `cancelled` (and dormant `paid` value not currently transitioned to). MVP delivery fee + tax hardcoded to 0.

**Seller signup flow**: register (multi-step wizard) → status `pending` → admin approves → status `approved` → can manage store/inventory. `/seller/signup/pending` blocks dashboard until approval. See `docs/seller_signup.md`.

**Store detail page** (`app/stores/[id]/page.tsx`, commit `31e0cc0`): Instacart-style 3-pane — services sidebar → categories → products with per-store inventory.

**Email dispatch**: OTP and order emails sent via Celery tasks (`worker.py`). Provider switch in `core/email.py` — `console` logs to stdout, `resend` does direct httpx POST (no SDK dep).

**CSS conventions**: Design tokens (CSS custom properties) in `frontend/src/styles/design-tokens.css`. Global utility classes (`btn`, `btn-primary`, etc.) in `frontend/src/app/globals.css`. Component scoping via `*.module.css`. **Never add Tailwind.**

**Async DB everywhere**: All routes use async sessions (`get_db_session`). When writing services, use `await session.exec(...)`, `await session.commit()`, `await session.refresh(obj)`.

## Git & GitHub Workflow

- **Never commit to `main`**. Always branch: `feat/`, `fix/`, `chore/`, `docs/`, `refactor/`, `test/`.
- **Conventional Commits**: `<type>(<scope>): <summary>` — imperative, ≤72 chars, no trailing period.
- **No AI co-author trailers** in commits/PRs.
- **Wait for explicit user approval before opening PRs**. Use `gh pr create` only.
- **Keep merged branches** — do not pass `--delete-branch`.
- All PRs: target `main`, must pass CI (lint + types + tests), squash-merge.
- Always use `gh` CLI for GitHub ops (`gh pr create/list/merge`, `gh issue *`, `gh run list`). Never raw `git push` + manual PR.

**Forbidden**: `git push --force` on shared branches, `--amend` on pushed commits, committing `.env`/secrets, `--no-verify`, direct commits to `main`.

## Additional Documentation

- `docs/architecture.md` — system topology, tech stack rationale, data model diagram
- `docs/flows.md` — guest cart, auth, cart sync, per-store checkout, order fulfillment, seller signup, catalog, inventory
- `docs/local_setup.md` — Docker + backend + frontend setup
- `docs/development_guide.md` — env vars, Alembic workflow, OTP/JWT, Celery, testing patterns, frontend conventions
- `docs/render_deployment.md` — Render Blueprint deployment, env vars, build/predeploy scripts
- `docs/seller_signup.md` — seller registration wizard, OTP 2-step flow, admin verify, layout guard
- `.claude/docs/architectural_patterns.md` — DI, model hierarchy, auth chain (any Firebase mention is stale)
- `TODO.md` — Phase tracker (Phases 1–4 complete, Phase 5 deployment in progress)

**Known TODOs surfaced during doc rewrite**:
- CORS in `backend/app/src/app/__init__.py` is hardcoded to `localhost:3000` — `render.yaml` provisions `FRONTEND_ORIGIN` but `config.py` does not read it. Wire up before production.
- No seller-approval/rejection email — seller learns via 30s status poll on `/seller/signup/pending`.
- `OrderStatus.Paid` defined but never assigned by state machine; `Payment.status` flips to `paid` only on `delivered`.
