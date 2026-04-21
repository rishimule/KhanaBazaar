# Khana Bazaar

Multi-vendor hyperlocal e-commerce platform for the Indian market (Instacart-like model).
Admins manage a master product catalog; sellers pick products and manage local inventory/pricing; customers shop per-store and pay via UPI.

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
- Brainstorming, plan-writing, or spec refinement (Superpowers `brainstorming`, `writing-plans`) — plan quality depends on you reading the code directly
- Reviewing a diff against a plan (Superpowers `requesting-code-review`)
- Small reads (1–3 specific files you already know you need)

**How to invoke:** describe the research task to the subagent in one message. It returns Gemini's raw output. You do the interpretation.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI (Python 3.12), Uvicorn ASGI |
| ORM / Migrations | SQLModel + Alembic (asyncpg driver) |
| Database | PostgreSQL 15 |
| Cache / Broker | Redis (Celery for background tasks) |
| Auth | Self-hosted email-OTP + JWT (PyJWT HS256, Resend) |
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
  - Required: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `OTP_PEPPER`
  - Optional: `EMAIL_PROVIDER` (default `console`), `RESEND_API_KEY`, `RESEND_FROM_EMAIL`
- Frontend: `frontend/.env.local` (see `frontend/.env.example`)
  - `NEXT_PUBLIC_API_URL` — backend base URL (default: `http://localhost:8000`)

## Git & GitHub Workflow

### Branch Strategy
- **Never commit directly to `main`.** All changes go through a feature branch and PR.
- Always `gh repo clone` or `git checkout -b` a new branch before making any code changes.
- Branch naming convention:
  - `feat/<short-description>` — new features
  - `fix/<short-description>` — bug fixes
  - `chore/<short-description>` — tooling, deps, config
  - `docs/<short-description>` — documentation only
  - `refactor/<short-description>` — refactors with no behavior change
  - `test/<short-description>` — adding or fixing tests

### Daily Workflow
```bash
# Start work on any task
git checkout main && git pull origin main
git checkout -b feat/my-feature

# ... make changes, run tests ...

git add <specific-files>          # never `git add .` blindly
git commit -m "feat: short description"

gh pr create ...                  # only after explicit user approval
```

### Commit Messages (Conventional Commits)
Format: `<type>(<optional scope>): <short summary>`

| Type | When to use |
|------|-------------|
| `feat` | New feature visible to users |
| `fix` | Bug fix |
| `chore` | Build, deps, tooling (no production code) |
| `docs` | Documentation only |
| `refactor` | Code change that is not a fix or feature |
| `test` | Adding or updating tests |
| `perf` | Performance improvement |
| `ci` | CI/CD pipeline changes |

- Summary line: ≤72 characters, imperative mood ("add X", not "added X")
- No period at end of summary
- Add a blank line + body for non-trivial commits explaining *why*, not *what*

### Pull Requests
- **Wait for explicit user permission before opening a PR.**
- Always use `gh pr create` (never raw `git push` + manual PR).
- PR title must follow the same Conventional Commits format as commit messages.
- PR body must include: Summary, Test plan, and any migration/env-var notes.
- Target branch is always `main` unless instructed otherwise.
- Keep PRs small and focused — one logical change per PR.
- Never force-push to `main` or any shared branch.

### GitHub CLI — Always Use `gh`
Use `gh` for all GitHub operations, never raw `git` equivalents:
```bash
gh repo view                      # view repo info
gh pr create                      # open a PR
gh pr list                        # list open PRs
gh pr merge                       # merge a PR
gh issue list / gh issue create   # manage issues
gh run list                       # check CI runs
```

### Code Review & Merge Rules
- All PRs require passing CI (lint + type-check + tests) before merge.
- Squash merge preferred to keep `main` history linear.
- Delete the feature branch after merging.
- Never merge your own PR without review in a team setting.

### What to Never Do
- `git push --force` on `main` or shared branches
- `git commit --amend` on already-pushed commits
- Committing `.env` files, secrets, or large binaries
- Skipping hooks with `--no-verify`
- Committing directly to `main`

## Additional Documentation

Check these files when working in the relevant area:

- [Architectural Patterns](.claude/docs/architectural_patterns.md) — DI patterns, model hierarchy, auth chain, state management conventions
- [Architecture Overview](docs/architecture.md) — Tech stack rationale, deployment strategy (Azure Container Apps)
- [User & Data Flows](docs/flows.md) — Guest cart, auth merge, checkout, order fulfillment flows
- [Local Setup](docs/local_setup.md) — Docker, backend, frontend setup walkthrough
- [Development Guide](docs/development_guide.md) — Firebase setup, env vars, Alembic workflow, troubleshooting
- [Roadmap](TODO.md) — Phase tracker (Phases 1-3 complete, Phase 4-5 in progress)
- [Seller Signup & Onboarding](docs/seller_signup.md) — Seller registration flow, OTP/token auth, wizard steps, pending approval, admin verify, layout guard
