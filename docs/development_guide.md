# Backend API & Infrastructure Setup Guide

This document supplies detailed step-by-step instructions, essential environment variables, and third-party account requirements needed for developers onboarding to Khana Bazaar, or those preparing the project for production deployment (Phase 5).

## 1. External Accounts & Services Required

Before deploying the Khana Bazaar backend to a live environment you must configure the following:

### Auth Setup (Email OTP)

No external auth service required. The backend generates 6-digit OTP codes and
emails them via Resend (or prints to stdout in dev mode).

#### Local dev

In `backend/app/.env`, set:

```ini
EMAIL_PROVIDER=console
JWT_SECRET=<any-32-char-string>
OTP_PEPPER=<any-16-char-string>
```

With `EMAIL_PROVIDER=console`, every OTP code is printed to the backend's
stdout — no real email is sent. Copy the code from the terminal when signing in
at http://localhost:3000/login.

#### Production (Resend)

1. Create a Resend account at https://resend.com, verify your sending domain.
2. Generate an API key and add to your deployment environment:

```ini
EMAIL_PROVIDER=resend
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=noreply@yourdomain.com
```

#### Test accounts

After running `uv run python scripts/seed_database.py`, sign in with:

| Role     | Email                        |
|----------|------------------------------|
| Admin    | admin@khanabazaar.dev        |
| Seller   | seller@khanabazaar.dev       |
| Customer | customer@khanabazaar.dev     |

Codes appear in backend stdout (console provider).

### Microsoft Azure
If deploying Phase 5, you will need an Azure subscription.
1. Create a resource group (e.g., `khanabazaar-prod-rg`) in **Central India (Pune)** and provision the following services:
   - **Azure Container Apps environment** (for hosting the FastAPI backend, Next.js frontend, and Celery worker).
   - **Azure Database for PostgreSQL – Flexible Server** (for managed PostgreSQL hosting).
   - **Azure Cache for Redis** (for the Celery broker and caching layer).
   - **Azure Container Registry (ACR)** (for storing Docker images).
   - **Azure Key Vault** (for secrets — connection strings, API keys — injected into Container Apps at runtime).
   - **Log Analytics workspace + Application Insights** (for centralized logging and request tracing).

## 2. Environment Variables (`.env`)

Create a `.env` file in the `backend/app/` directory. Pydantic-Settings will automatically load these variables.

```ini
# --- Core Application Variables ---
PROJECT_NAME="Khana Bazaar API"
VERSION="0.1.0"
ENVIRONMENT="development" # Set to "production" in live environments

# --- Database (PostgreSQL) ---
# Format: postgresql+asyncpg://user:password@host:port/dbname
DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar"

# --- Broker/Cache (Redis) ---
# Format: redis://host:port/db_index
REDIS_URL="redis://localhost:6379/0"

# --- Auth (JWT + OTP) ---
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET="change-me-use-secrets-token-hex-32"
JWT_EXPIRES_HOURS=24

# Generate with: python -c "import secrets; print(secrets.token_hex(16))"
OTP_PEPPER="change-me-use-secrets-token-hex-16"

# Email: "console" (prints codes to stdout) or "resend" (production)
EMAIL_PROVIDER="console"
RESEND_API_KEY=""
RESEND_FROM_EMAIL=""
```

## 3. Local Development & Maintenance Guide

### Step 1: Spin Up Infrastructure (Docker)
Ensure your local Docker daemon is running, then start the managed dependencies (Postgres and Redis).
```bash
# Start PostgreSQL Database
docker run -d --name kb-postgres -e POSTGRES_PASSWORD=password -e POSTGRES_DB=khanabazaar -p 5432:5432 postgres:15

# Start Redis Message Broker
docker run -d --name kb-redis -p 6379:6379 redis:alpine
```

### Step 2: Install Python Dependencies
Khana Bazaar utilizes `uv` for lightning-fast dependency resolution.
```bash
cd backend/app
uv sync
```
*(If dependencies fail, run: `uv add fastapi uvicorn sqlmodel asyncpg alembic celery redis pydantic-settings pyjwt httpx email-validator`)*

### Step 3: Run Database Migrations (Alembic)
Whenever the SQLModel schemas in `models/` change, you must auto-generate and apply Alembic migrations.
```bash
# 1. Generate the migration script (Do this after editing models)
uv run alembic revision --autogenerate -m "Description of changes"

# 2. Apply the migration to the database
uv run alembic upgrade head
```
**TIP:** *If your local schema gets corrupted or out-of-sync during testing, it is entirely safe to drop the `public` schema using `psql` or `pgAdmin` and re-run `alembic upgrade head` to rebuild the tables cleanly.*

### Step 4: Run the FastAPI ASGI Server
Boot the web server with hot-reloading for local development.
```bash
uv run uvicorn app.main:app --reload
```
- Open `http://localhost:8000/docs` to view the interactive Swagger REST API documentation.

### Step 5: Start the Celery Worker
Background tasks (like sending emails or caching heavy datasets) are piped to Celery. The worker requires a dedicated terminal window.
```bash
cd backend/app
uv run celery -A app.core.celery_app worker --loglevel=info
```
**TIP:** *If tasks are mysteriously getting stuck in the queue, verify that your `REDIS_URL` is correct and that the `kb-redis` docker container hasn't crashed. You can test the queue manually by hitting `POST /api/v1/tasks/test-celery` via the Swagger docs.*

### Step 6: Testing Best Practices
Integration tests run against a separate `khanabazaar_test` PostgreSQL database (not in-memory). Unit tests for JWT and OTP use fakeredis and need no DB.
Ensure `docker-compose up -d` is running before running the full suite.

To execute the test suite:
```bash
cd backend/app
uv run pytest -v
```

## 4. Common Troubleshooting Tips

1. **Mypy "Untyped Decorator" Errors:** Python's static type checker (Mypy) struggles with dynamic library injections (like `@celery_app.task`). If the CI pipeline fails on this, add `# type: ignore` to the end of the decorator line to suppress it.
2. **OTP / 401 Errors:** If `POST /auth/otp/verify` returns 401, check that `JWT_SECRET` in `.env` is set and that the token hasn't expired (default 24 h). For dev, `EMAIL_PROVIDER=console` prints codes to backend stdout.
3. **Database Connection Refused:** This almost universally means the Postgres docker container is stopped, or the password specified in `DATABASE_URL` doesn't match the one used during the `docker run` initialization. Check `docker ps` to confirm.
