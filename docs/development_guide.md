# Backend API & Infrastructure Setup Guide

This document supplies detailed step-by-step instructions, essential environment variables, and third-party account requirements needed for developers onboarding to Khana Bazaar, or those preparing the project for production deployment (Phase 5).

## 1. External Accounts & Services Required

Before deploying the Khana Bazaar backend to a live environment (or fully testing authentic authentication locally), you must create and configure the following third-party provider accounts:

### Firebase (Authentication & RBAC)
Khana Bazaar relies on Firebase Authentication to securely handle user identities, phone numbers (OTPs), and role assignments.
1. **Create Project:** Go to the [Firebase Console](https://console.firebase.google.com/) and create a new project (e.g., `khanabazaar-prod`).
2. **Enable Auth Providers:** Navigate to **Authentication > Sign-in method** and enable the following providers:
   - **Phone Number:** Essential for the primary Indian market user base.
   - **Email/Password:** Recommended for creating the initial App Admin accounts.
3. **Generate Admin SDK Key (Crucial for Backend):**
   - Our FastAPI backend needs admin privileges to verify user tokens securely.
   - Go to **Project Settings > Service Accounts**.
   - Click **Generate new private key**.
   - Save the `.json` file securely (e.g., `firebase-admin-key.json`).
   - **Do NOT commit this file to version control.**

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

# --- Firebase Configuration ---
# In development, the placeholder "khanabazaar-dev" is used for mocking tests. 
# Make sure to input your actual Project ID from Step 1.
FIREBASE_PROJECT_ID="khanabazaar-prod" 

# REQUIRED for the Firebase Admin SDK to authenticate.
# Point this to the absolute path of the JSON key you downloaded earlier.
# In Azure Container Apps, this is usually mounted from Azure Key Vault as a secret reference.
GOOGLE_APPLICATION_CREDENTIALS="/absolute/path/to/firebase-admin-key.json"
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
*(If dependencies fail, manually inject environments: `uv add fastapi uvicorn sqlmodel asyncpg alembic celery redis pydantic-settings firebase-admin pytest httpx`)*

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
The Khana Bazaar integration tests are engineered to bypass your local Postgres instance completely to prevent destructive teardowns on your development data. They isolate into `sqlite+aiosqlite:///:memory:`.

To execute the test suite:
```bash
cd backend/app
uv run pytest -v
```

## 4. Common Troubleshooting Tips

1. **Mypy "Untyped Decorator" Errors:** Python's static type checker (Mypy) struggles with dynamic library injections (like `@celery_app.task`). If the CI pipeline fails on this, add `# type: ignore` to the end of the decorator line to suppress it.
2. **Firebase Token Verification Failures:** If you are testing requests against real Firebase JWT tokens locally but get a 401 Unauthorized, double-check that `GOOGLE_APPLICATION_CREDENTIALS` is physically exported in your terminal session before launching Uvicorn:
   `export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json && uv run uvicorn app.main:app`
3. **Database Connection Refused:** This almost universally means the Postgres docker container is stopped, or the password specified in `DATABASE_URL` doesn't match the one used during the `docker run` initialization. Check `docker ps` to confirm.
