# Local Development Setup Guide

This guide details how to set up the Khana Bazaar project locally for development. We'll use Docker to emulate our production Azure environment so that when we are ready to deploy, the transition is seamless.

## Architecture Consistency (Local vs. Azure)

To ensure our local environment mirrors our target Azure deployment without incurring unnecessary costs during development, we map services as follows:

| Component                  | Local Development                        | Azure Deployment                                         |
| :------------------------- | :--------------------------------------- | :------------------------------------------------------- |
| **Backend API**            | FastAPI running via Uvicorn (Hot Reload) | Azure Container Apps                                     |
| **Frontend**               | Next.js Node server (Hot Reload)         | Azure Container Apps                                     |
| **Database**               | PostgreSQL Docker Container              | Azure Database for PostgreSQL – Flexible Server          |
| **Message Broker / Cache** | Redis Docker Container                   | Azure Cache for Redis                                    |
| **Background Tasks**       | Celery Worker (Local Process)            | Azure Container Apps (worker revision, min-replicas ≥ 1) |
| **Media Storage**          | Local File System (`/uploads` dir)       | Azure Blob Storage                                       |

## Prerequisites

Before starting, ensure you have the following installed on your local machine:

1.  **Docker & Docker Compose**: For running PostgreSQL and Redis containers.
2.  **Python 3.10+**: For the FastAPI backend.
3.  **Node.js 18+**: For the Next.js frontend.
4.  **Git**: For version control.

## 1. Local Database & Cache Setup (Docker)

The repository already includes a root-level `docker-compose.yml` for the local
Postgres and Redis services.

1.  **Start the required services**:
    ```bash
    docker compose up -d postgres redis
    ```
    This uses the checked-in Compose file and starts the `postgres` and `redis`
    services without touching the backend or frontend processes.
2.  **Reset local state when you need a clean canonical dataset**:
    ```bash
    ./scripts/reset_local_state.sh
    ```
    This reset is local-only. It deletes the `postgres_data` and `redis_data`
    volumes, recreates the database schema via Alembic, reseeds the app with the
    canonical development dataset, and does not rebuild any Docker images.

## 2. Backend Setup (FastAPI)

While we could run the backend in Docker locally, it is often faster to run it directly on your machine to take advantage of IDE debuggers and hot-reloading.

1.  **Create a Virtual Environment**:
    ```bash
    cd backend/app
    python -m venv venv
    source venv/bin/activate  # On Linux/macOS
    ```
2.  **Install Dependencies**:
    - We will use `pip` to install packages like `fastapi`, `uvicorn`, `sqlalchemy`, `asyncpg`, `celery`, and `redis`.
3.  **Environment Variables (`.env`)**:
    Create a `.env` file in the `backend/` directory pointing to your local Docker services:
    ```ini
    DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar
    REDIS_URL=redis://localhost:6379/0
    ENVIRONMENT=development
    ```
4.  **Database seed entrypoints**:
    - The canonical local dataset entrypoint is `backend/app/scripts/seed_database.py`.
    - `backend/app/scripts/seed_seller_applications.py` is only a compatibility
      wrapper for the admin-review subset and is not the full development seed.
5.  **Run the local server**:
    ```bash
    uv run uvicorn app:app --reload --host 0.0.0.0 --port 8000
    ```

## 3. Frontend Setup (Next.js)

1.  **Initialize the application**:
    ```bash
    cd frontend
    npm install
    ```
2.  **Environment Variables (`.env.local`)**:
    Create a `.env.local` file pointing to your local FastAPI backend:
    ```ini
    NEXT_PUBLIC_API_URL=http://localhost:8000
    ```
3.  **Run the local development server**:
    ```bash
    npm run dev
    ```

## 4. Preparing for Azure (Code Design Practices)

While developing locally, we must adhere to the **Twelve-Factor App** principles to ensure the code is "Azure-Ready" from day one:

1.  **Stateless Compute**: Container Apps replicas can be destroyed or spun up at any time. **Never** store session data or file uploads in the container's memory or local disk.
    - _Solution:_ Always use Redis for sessions/carts, and abstract file storage so we can swap local disk saving for Azure Blob Storage later.
2.  **Strict Configuration Management**: Never hardcode connection strings or API keys. Always read them from `os.environ` (Python) or `process.env` (Node). This allows us to inject Azure Key Vault secrets during deployment without changing code.
3.  **Health Checks**: Implement root endpoints (`/health` or `/ping`) in both FastAPI and Next.js. Azure Container Apps will use these to determine if the container deployed successfully and is ready to receive traffic.
