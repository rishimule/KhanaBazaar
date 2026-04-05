# Khana Bazaar

Multi-vendor hyperlocal e-commerce platform for the Indian market (Instacart-like model).
Admins manage a master product catalog; sellers pick products and manage local inventory/pricing; customers shop per-store and pay via UPI.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI (Python 3.12), Uvicorn ASGI |
| ORM / Migrations | SQLModel + Alembic (asyncpg driver) |
| Database | PostgreSQL 15 |
| Cache / Broker | Redis (Celery for background tasks) |
| Auth | Firebase Admin SDK (phone OTP + email) |
| Config | Pydantic-Settings (`.env` files) |
| Frontend | Next.js 16 (App Router), React 19, TypeScript |
| Frontend styling | CSS Modules + design tokens (no Tailwind) |
| PWA | Service worker + manifest.json |
| Package mgmt | `uv` (backend), `npm` (frontend) |
| Linting/Types | Ruff + Mypy (backend), ESLint + TypeScript (frontend) |
| Testing | Pytest + pytest-asyncio (backend) |

## Project Structure

```
backend/app/                 # FastAPI application root (run commands from here)
  src/app/
    main.py                  # Uvicorn entrypoint
    __init__.py              # FastAPI app instance, route mounting
    api/                     # Route handlers (auth, catalog, stores, tasks)
    core/                    # Config, security (Firebase), Celery setup
    db/                      # Async DB session factory
    models/                  # SQLModel table definitions (base, catalog, store)
    worker.py                # Celery task definitions
  migrations/                # Alembic migration versions
  tests/                     # Pytest integration tests
  pyproject.toml             # Dependencies, tool config (ruff, mypy, pytest)
frontend/
  src/
    app/                     # Next.js App Router pages
      stores/                # Store listing + [id] detail page
      cart/                  # Shopping cart page
      seller/                # Seller dashboard + inventory management
      admin/                 # Admin dashboard (categories, products)
    components/              # Shared UI (Navbar, Footer, ProductCard, Modal, etc.)
    lib/                     # API client, cart logic (localStorage), CartContext
    types/                   # TypeScript interfaces mirroring backend models
    styles/                  # Design tokens (CSS custom properties)
docs/                        # Architecture, flows, setup guides
docker-compose.yml           # Local Postgres + Redis
```

## Essential Commands

### Infrastructure
```bash
docker-compose up -d                    # Start Postgres + Redis
```

### Backend (from `backend/app/`)
```bash
uv sync                                 # Install dependencies
uv run alembic upgrade head             # Apply DB migrations
uv run alembic revision --autogenerate -m "description"  # Generate migration
uv run uvicorn app.main:app --reload    # Start API server (port 8000)
uv run celery -A app.core.celery_app worker --loglevel=info  # Start Celery worker
uv run pytest -v                        # Run tests (requires khanabazaar_test DB)
uv run ruff check .                     # Lint
uv run mypy .                           # Type check
```

### Frontend (from `frontend/`)
```bash
npm install                             # Install dependencies
npm run dev                             # Start dev server (port 3000)
npm run build                           # Production build
npm run lint                            # ESLint
```

### API Documentation
Swagger UI available at `http://localhost:8000/docs` when backend is running.
All API routes are prefixed with `/api/v1` (see `backend/app/src/app/core/config.py:9`).

## RBAC Roles

Three roles defined in `backend/app/src/app/models/base.py:8-11`: **Admin**, **Seller**, **Customer**.
- Public endpoints: list products, list stores, list inventory, health check
- Seller endpoints: create store, manage inventory (also accessible by Admin)
- Admin endpoints: create categories, create master products

## Testing

Tests use a **separate Postgres database** (`khanabazaar_test`) — not SQLite in-memory.
Auth dependencies are overridden via `app.dependency_overrides` in test fixtures.
See `backend/app/tests/conftest.py` for DB setup and `test_stores.py` for the override pattern.

## Environment Variables

- Backend: `backend/app/.env` (see `backend/app/.env.example`)
  - Required: `DATABASE_URL`, `REDIS_URL`, `FIREBASE_PROJECT_ID`
  - Optional: `GOOGLE_APPLICATION_CREDENTIALS` (path to Firebase service account key)
- Frontend: `frontend/.env.local` (see `frontend/.env.example`)
  - `NEXT_PUBLIC_API_URL` — backend base URL (default: `http://localhost:8000`)

## Additional Documentation

Check these files when working in the relevant area:

- [Architectural Patterns](.claude/docs/architectural_patterns.md) — DI patterns, model hierarchy, auth chain, state management conventions
- [Architecture Overview](docs/architecture.md) — Tech stack rationale, deployment strategy (GCP Cloud Run)
- [User & Data Flows](docs/flows.md) — Guest cart, auth merge, checkout, order fulfillment flows
- [Local Setup](docs/local_setup.md) — Docker, backend, frontend setup walkthrough
- [Development Guide](docs/development_guide.md) — Firebase setup, env vars, Alembic workflow, troubleshooting
- [Roadmap](TODO.md) — Phase tracker (Phases 1-3 complete, Phase 4-5 in progress)
