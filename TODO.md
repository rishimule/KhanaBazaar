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

## Phase 5: Deployment & CI/CD (Azure)
- [x] Author `infra/modules/meilisearch.bicep` (Meilisearch Container App + Azure Files share for `/meili_data`).
- [ ] Write `Dockerfile` for `backend/app/` (api + worker share the image; beat reuses worker image with different entrypoint).
- [ ] Write `Dockerfile` for `frontend/` and enable `output: "standalone"` in `next.config.ts`.
- [ ] Author `infra/main.bicep` + `infra/main.parameters.json` + top-level `azure.yaml` (azd service map: api, worker, beat, web; references the committed Meilisearch module).
- [ ] Author remaining Bicep modules: `network.bicep`, `container-env.bicep`, `acr.bicep`, `keyvault.bicep`, `postgres.bicep`, `redis.bicep`, `appinsights.bicep`, `container-app-{api,worker,beat,web}.bicep`, `migration-job.bicep`, `frontdoor.bicep`.
- [ ] Provision Azure subscription + resource groups (`kb-prod-rg`, `kb-network-rg`) and bootstrap GitHub Actions OIDC federated credentials (push-to-main subject + `pull_request` subject).
- [ ] First `azd up` against `centralindia`: ACA env + Postgres Flexible Server (B1ms, PostGIS extension) + Redis Basic C0 + ACR Basic + Key Vault + Log Analytics + App Insights.
- [ ] Wire OpenTelemetry into `backend/app/src/app/__init__.py` (`azure-monitor-opentelemetry.configure_azure_monitor()` guarded on `APPLICATIONINSIGHTS_CONNECTION_STRING`).
- [ ] Author `.github/workflows/deploy.yml` (lint + types + tests → `az acr build` → `containerapp job update + start` for migrations → `containerapp update` with `--revision-suffix` per service → smoke test).
- [ ] Decide Front Door tier (Premium for managed WAF + Private Link to Container Apps, or Standard with app-layer `X-Azure-FDID` enforcement) and provision custom domain + managed TLS.
- [ ] First production reindex: `uv run python -m app.search.reindex --all` from a one-shot Container Apps Job.

## Phase 6: Future Enhancements (Payments)
- [ ] Integrate Razorpay (or other payment gateways) for UPI checkout intent flows.
