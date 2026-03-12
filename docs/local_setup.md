# Local Development Setup Guide

This guide details how to set up the Khana Bazaar project locally for development. We'll use Docker to emulate our production GCP environment so that when we are ready to deploy, the transition is seamless.

## Architecture Consistency (Local vs. GCP)
To ensure our local environment mirrors our target GCP deployment without incurring unnecessary costs during development, we map services as follows:

| Component | Local Development | GCP Deployment |
| :--- | :--- | :--- |
| **Backend API** | FastAPI running via Uvicorn (Hot Reload) | GCP Cloud Run |
| **Frontend** | Next.js Node server (Hot Reload) | GCP Cloud Run |
| **Database** | PostgreSQL Docker Container | GCP Cloud SQL |
| **Message Broker / Cache** | Redis Docker Container | GCP Memorystore (Redis) |
| **Background Tasks** | Celery Worker (Local Process) | Cloud Run (Background) |
| **Media Storage** | Local File System (`/uploads` dir) | GCP Cloud Storage |

## Prerequisites
Before starting, ensure you have the following installed on your local machine:
1.  **Docker & Docker Compose**: For running PostgreSQL and Redis containers.
2.  **Python 3.10+**: For the FastAPI backend.
3.  **Node.js 18+**: For the Next.js frontend.
4.  **Git**: For version control.

## 1. Local Database & Cache Setup (Docker)

We'll use Docker Compose to spin up our stateful services (Postgres and Redis).

1.  **Create a `docker-compose.yml` file** in the root of the project (we will create this in the next phase). This file will define:
    *   A `postgres:15` service.
    *   A `redis:alpine` service.
2.  **Start the services**:
    ```bash
    docker-compose up -d
    ```
    *(Note: This keeps your main system clean and ensures the database runs exactly as it would in production).*

## 2. Backend Setup (FastAPI)

While we could run the backend in Docker locally, it is often faster to run it directly on your machine to take advantage of IDE debuggers and hot-reloading.

1.  **Create a Virtual Environment**:
    ```bash
    cd backend
    python -m venv venv
    source venv/bin/activate  # On Linux/macOS
    ```
2.  **Install Dependencies**:
    *   We will use `pip` to install packages like `fastapi`, `uvicorn`, `sqlalchemy`, `asyncpg`, `celery`, and `redis`.
3.  **Environment Variables (`.env`)**:
    Create a `.env` file in the `backend/` directory pointing to your local Docker services:
    ```ini
    DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar
    REDIS_URL=redis://localhost:6379/0
    ENVIRONMENT=development
    ```
4.  **Run the local server**:
    ```bash
    uvicorn main:app --reload
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

## 4. Preparing for GCP (Code Design Practices)

While developing locally, we must adhere to the **Twelve-Factor App** principles to ensure the code is "GCP-Ready" from day one:

1.  **Stateless Compute**: Cloud Run containers can be destroyed or spun up at any time. **Never** store session data or file uploads in the container's memory or local disk.
    *   *Solution:* Always use Redis for sessions/carts, and abstract file storage so we can swap local disk saving for GCP Cloud Storage later.
2.  **Strict Configuration Management**: Never hardcode connection strings or API keys. Always read them from `os.environ` (Python) or `process.env` (Node). This allows us to inject GCP Secret Manager secrets during deployment without changing code.
3.  **Health Checks**: Implement root endpoints (`/health` or `/ping`) in both FastAPI and Next.js. GCP Cloud Run will use these to determine if the container deployed successfully and is ready to receive traffic.
