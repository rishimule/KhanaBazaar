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

## Phase 5: Deployment & CI/CD (Google Cloud Platform)

Target architecture, cost model, and full runbook: [`docs/gcp_deployment.md`](docs/gcp_deployment.md). Single region `asia-south1` (Mumbai), managed serverless throughout (Cloud Run + Cloud SQL + Memorystore).

- [ ] Write `Dockerfile` for `backend/app/` (api + worker share the image; beat reuses it with a different `CMD`).
- [ ] Write `Dockerfile` for `frontend/` and enable `output: "standalone"` in `next.config.ts`.
- [ ] Author `deploy/gcp/cloudrun-{api,worker,beat,web,meili}.yaml` Cloud Run service manifests (meili gets a GCS Fuse mount for `/meili_data`, internal ingress).
- [ ] Author Terraform under `infra/`: VPC + Direct VPC egress (or Serverless VPC Connector), Cloud SQL (`db-f1-micro`, PostGIS extension, private IP), Memorystore Redis (Basic 1 GiB), Artifact Registry repo, Secret Manager secrets, Workload Identity Federation pool + provider.
- [ ] Create the GCP project + link billing + enable APIs (`run`, `sqladmin`, `redis`, `artifactregistry`, `secretmanager`, `storage`, `vpcaccess`, `servicenetworking`, `compute`, IAM, logging, monitoring) — see `docs/gcp_deployment.md` §4.
- [ ] Bootstrap GitHub Actions → GCP via Workload Identity Federation (push-to-`main` + `pull_request` subjects; no long-lived SA keys).
- [ ] First deploy: provision data services, push images to Artifact Registry, run the one-shot `khanabazaar-migrate` Cloud Run Job (`alembic upgrade head`), deploy the five Cloud Run services.
- [ ] Wire OpenTelemetry → Cloud Trace into `backend/app/src/app/__init__.py` (`opentelemetry-exporter-gcp-trace`, guarded on a `GOOGLE_CLOUD_PROJECT` / OTEL env var). Launch blocker.
- [ ] Author `.github/workflows/deploy.yml` (lint + types + tests → Cloud Build / `gcloud builds submit` → migrate Job → `gcloud run deploy` per service with a new revision → smoke test).
- [ ] Set up custom domain + managed TLS via Cloud Run domain mapping; set a billing budget alert (~₹6,500 / $80) before go-live.
- [ ] First production reindex: `uv run python -m app.search.reindex --all` from a one-shot Cloud Run Job.

## Phase 6: Future Enhancements (Payments)
- [ ] Integrate Razorpay (or other payment gateways) for UPI checkout intent flows.
