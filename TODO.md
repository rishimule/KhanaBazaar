<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
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

## Phase 5: Deployment & CI/CD (GCP) — DONE / LIVE
- [x] Backend + frontend Dockerfiles; `frontend` bakes `INTERNAL_API_URL` at build time.
- [x] `deploy/gcp/bootstrap.sh` — APIs, Artifact Registry, VPC + firewall, Cloud SQL (PostGIS), Secret Manager, runtime + deployer service accounts, Workload Identity Federation.
- [x] e2-small VM `kb-svc` (docker-compose: Celery worker+beat, Redis, Meilisearch, cloud-sql-proxy).
- [x] Cloud Run `khanabazaar-web` + `khanabazaar-api` (always-warm, Direct VPC egress, Cloud SQL connector).
- [x] `kb-migrate` Cloud Run Job — alembic migrate → idempotent seed → `python -m app.search.reindex --all`.
- [x] CI/CD: `.github/workflows/deploy.yml` — merge to `main` builds + deploys api/web and restarts the worker on the VM (GitHub Actions + WIF).
- [x] Custom domain `https://khanabazaar.rishimule.dev` via Firebase Hosting; billing budget alert at 20000 INR.
- [ ] Real-launch hardening (post-MVP): switch to Resend + Twilio, set `ENVIRONMENT=production` (disables dev-mailbox), rotate secrets, Cloud NAT static egress IP for the Maps server key, wire OpenTelemetry / Cloud Trace in `backend/app/src/app/__init__.py`.

## Phase 6: Future Enhancements (Payments)
- [ ] Integrate Razorpay (or other payment gateways) for UPI checkout intent flows.
