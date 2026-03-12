# Project Tasks & Roadmap

This file tracks the upcoming features, bug fixes, and general to-dos for the Khana Bazaar platform.

## Phase 1: Planning & Setup
- [x] Initial project architectural design and tech stack selection.
- [x] Create standardized project documentation files.
- [x] Initialize Git repository.
- [x] Setup local Docker Compose (Postgres, Redis).
- [x] Define project structure (backend/ and frontend/ dirs).

## Phase 2: Backend Development (FastAPI)
- [ ] Setup FastAPI project structure and dependency management via `uv` (Ruff, Mypy, Pytest).
- [ ] Configure PostgreSQL database connection using SQLModel and asyncpg.
- [ ] Initialize Alembic for database migrations.
- [ ] Implement user authentication and RBAC (Admin, Seller, Customer roles).
- [ ] Develop Master Catalog management APIs.
- [ ] Develop Seller inventory management APIs.
- [ ] Set up Uvicorn ASGI server and Pydantic-Settings for configuration management.
- [ ] Set up Redis and Celery (Python Client) for background tasks.
- [ ] Write integration and unit tests using Pytest and pytest-asyncio.

## Phase 3: Frontend Development (Next.js)
- [ ] Initialize Next.js PWA project.
- [ ] Configure UI library (e.g., Tailwind CSS or Vanilla CSS) and design system.
- [ ] Build global UI components (Navbar, Footer, Product Cards).
- [ ] Develop Customer storefront and shopping cart.
- [ ] Develop Seller portal dashboard.
- [ ] Develop Admin dashboard for catalog management.

## Phase 4: Integration & Payments
- [ ] Integrate Razorpay for UPI checkout intent flows.
- [ ] Connect Frontend interfaces with FastAPI endpoints.
- [ ] End-to-end testing of the complete order flow.

## Phase 5: Deployment & CI/CD (GCP)
- [ ] Setup GCP project, configure IAM, and enable necessary APIs (Cloud Run, Cloud SQL, Cloud Storage, Redis).
- [ ] Dockerize backend and frontend applications via `Dockerfile`.
- [ ] Configure GitHub Actions for CI/CD pipelines.
- [ ] Deploy databases and services to GCP (Cloud SQL, Cloud Run).
- [ ] Configure CDN for media assets via GCP Cloud Storage.
