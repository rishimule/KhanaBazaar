# Project Tasks & Roadmap

This file tracks the upcoming features, bug fixes, and general to-dos for the Khana Bazaar platform.

## Phase 1: Planning & Setup
- [x] Initial project architectural design and tech stack selection.
- [x] Create standardized project documentation files.
- [x] Initialize Git repository.
- [x] Setup local Docker Compose (Postgres, Redis).
- [x] Define project structure (backend/ and frontend/ dirs).

## Phase 2: Backend Development (FastAPI)
- [x] Setup FastAPI project structure and dependency management via `uv` (Ruff, Mypy, Pytest).
- [x] Configure PostgreSQL database connection using SQLModel and asyncpg.
- [x] Initialize Alembic for database migrations.
- [x] Implement user authentication and RBAC (Admin, Seller, Customer roles).
- [x] Develop Master Catalog management APIs.
- [x] Develop Seller inventory management APIs.
- [x] Set up Uvicorn ASGI server and Pydantic-Settings for configuration management.
- [x] Set up Redis and Celery (Python Client) for background tasks.
- [x] Write integration and unit tests using Pytest and pytest-asyncio.

## Phase 3: Frontend Development (Next.js)
- [x] Initialize Next.js PWA project.
- [x] Configure UI library (e.g., Tailwind CSS or Vanilla CSS) and design system.
- [x] Build global UI components (Navbar, Footer, Product Cards).
- [x] Develop Customer storefront and shopping cart.
- [x] Develop Seller portal dashboard.
- [x] Develop Admin dashboard for catalog management.

## Phase 4: Integration
- [x] Connect Frontend interfaces with FastAPI endpoints.
- [x] End-to-end testing of the complete order flow (simulated checkout).

## Phase 5: Deployment & CI/CD (Azure)
- [ ] Provision Azure subscription + resource group, configure RBAC, and create core resources (Azure Container Apps environment, Azure Database for PostgreSQL Flexible Server, Azure Cache for Redis, Azure Container Registry, Azure Key Vault, Log Analytics + Application Insights).
- [ ] Dockerize backend and frontend applications via `Dockerfile`.
- [ ] Configure GitHub Actions with OIDC federated credentials to Azure for CI/CD pipelines (build → ACR → ACA).
- [ ] Deploy database and services to Azure (Azure Database for PostgreSQL Flexible Server, Azure Container Apps).
- [ ] Configure CDN for media assets via Azure Front Door in front of Azure Blob Storage.

## Phase 6: Future Enhancements (Payments)
- [ ] Integrate Razorpay (or other payment gateways) for UPI checkout intent flows.
