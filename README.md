# Khana Bazaar

Multi-vendor hyperlocal e-commerce platform for the Indian market — Instacart-style, with admin-curated catalogs, seller-managed local inventory, and UPI checkout.

- **Admins** maintain a master product catalog (services, categories, subcategories, master products) — multi-lingual (en, hi, mr, gu, pa).
- **Sellers** register, get admin-approved, run **one store** with **multiple services** (Grocery, Food, Pharmacy, …), and manage per-store inventory + pricing.
- **Customers** shop one store at a time, pay via UPI, and check out per-store.

Auth is **email-OTP + JWT** — no passwords, no Firebase.

## Tech Stack

| Layer | Stack |
|------|------|
| Backend | FastAPI 0.135, Python 3.12, Uvicorn, SQLModel + Alembic, asyncpg |
| Database | PostgreSQL 15 |
| Cache / Broker | Redis 7, Celery 5.6 |
| Auth | Self-hosted email-OTP + JWT (PyJWT HS256) |
| Email | `console` (dev) / `resend` (prod, raw httpx) |
| Frontend | Next.js 16.1 (App Router), React 19.2, TypeScript 5, CSS Modules + design tokens |
| PWA | `frontend/public/sw.js` + `manifest.json` |
| Tooling | `uv` (backend), `npm` (frontend), Ruff + Mypy, ESLint 9, Pytest |
| Deploy | Microsoft Azure (Container Apps + Postgres Flexible Server + Cache for Redis), provisioned via Bicep + `azd` |

## Repo Layout

```
backend/app/             FastAPI service (run from here)
  src/app/api/           Routers — auth, catalog, stores, sellers, customers, carts, orders, tasks, meta
  src/app/core/          config, security, otp, email, redis, celery_app, rate_limit
  src/app/models/        SQLModel tables
  src/app/services/      Business logic (checkout, orders, inventory, …)
  src/app/schemas/       Pydantic request/response models
  src/app/worker.py      Celery tasks
  migrations/            Alembic versions
  tests/                 Pytest suite (uses real Postgres `khanabazaar_test`)
  scripts/               seed_database.py, seed_seller_applications.py
frontend/src/
  app/                   Next.js App Router (stores, cart, checkout, account, seller, admin)
  components/            Navbar, Footer, DashboardLayout, DataTable, Modal, ProductCard, …
  lib/                   api, AuthContext, CartContext, orders, format-address
  styles/                design-tokens.css, globals.css
docs/                    architecture, flows, local_setup, development_guide, azure_deployment, seller_signup
scripts/                 dev.sh, reset_local_state.sh
```

## Prerequisites

- Docker + Docker Compose
- Python 3.12 + [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ + npm

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
# Postgres + Redis
docker compose up -d postgres redis

# Backend
cd backend/app
uv sync
uv run alembic upgrade head
uv run python scripts/seed_database.py
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

Brings up Postgres + Redis (Docker), backend (Uvicorn :8000), Celery worker, and frontend (Next.js :3000). Logs land in `.dev/logs/`.

```bash
./scripts/dev.sh status              # pids + docker (incl. ngrok URL when tunnel up)
./scripts/dev.sh logs backend        # tail single log (also: celery, frontend, ngrok)
./scripts/dev.sh stop                # stop app procs (incl. tunnel)
./scripts/dev.sh stop --all          # also stop Postgres + Redis
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

API docs: http://localhost:8000/docs · Frontend: http://localhost:3000 · All routes prefixed `/api/v1`.

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
uv run pytest -v                                  # test suite (needs khanabazaar_test DB)
uv run ruff check .                               # lint
uv run mypy .                                     # type-check
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
| `JWT_EXPIRES_HOURS` | no | `24` |
| `OTP_TTL_SECONDS` | no | `600` |
| `OTP_MAX_ATTEMPTS` | no | `5` |
| `OTP_RESEND_COOLDOWN` | no | `60` |
| `OTP_MAX_PER_HOUR` | no | `5` |
| `EMAIL_PROVIDER` | no | `console` (`resend` for prod) |
| `RESEND_API_KEY` / `RESEND_FROM_EMAIL` | only if `resend` | — |
| `FRONTEND_ORIGIN` | no | `http://localhost:3000,http://127.0.0.1:3000` |

### Frontend — `frontend/.env.local`

| Var | Default |
|-----|---------|
| `NEXT_PUBLIC_API_URL` | `""` (empty — Next.js `rewrites()` proxies `/api/v1/*` to the backend) |

## Deployment

Microsoft Azure — Container Apps (api, worker, web) + Postgres Flexible Server + Cache for Redis, fronted by Azure Front Door. Infra is Bicep + `azd up`; CI/CD is GitHub Actions with OIDC. See [`docs/azure_deployment.md`](docs/azure_deployment.md).

## Documentation

- [Architecture](docs/architecture.md) — topology, stack rationale, data model
- [Flows](docs/flows.md) — guest cart, OTP auth, cart sync, per-store checkout, seller signup
- [Local setup](docs/local_setup.md)
- [Development guide](docs/development_guide.md) — Alembic, OTP/JWT, Celery, testing
- [Seller signup](docs/seller_signup.md) — wizard, 2-step OTP, admin approval
- [Azure deployment](docs/azure_deployment.md)
- [Phase tracker](TODO.md)

## Contributing

- Branch off `main`: `feat/`, `fix/`, `chore/`, `docs/`, `refactor/`, `test/`.
- Conventional Commits — `<type>(<scope>): <summary>`, ≤72 chars, no trailing period.
- PRs target `main`, must pass CI (lint + types + tests), merged via merge-commit (`gh pr merge --merge`).
- Never commit `.env` / secrets; never `git push --force` on shared branches.
