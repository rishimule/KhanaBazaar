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

## Returns (Return Order Management BRD) — DONE
- [x] `return_request` / `return_request_item` / `return_event` aggregate + state machine (7 resting states).
- [x] Three OTP events: customer-typed initiation, seller-typed handover receipt, customer-typed payment receipt.
- [x] Settlement split — postpaid credit reversal first, then store credit or confirmed cash.
- [x] `customer_store_credit` ledger (seller owes customer) + auto-apply at checkout with opt-out.
- [x] Per-service `return_window_days` (seller + admin endpoints, audited).
- [x] Admin parity + force accept/reject/close with mandatory reason and audit rows.
- [x] In-app + email (6 templates) + WhatsApp (5 templates) on every return event.
- [x] Hourly expiry sweep for both stalled stages.
- [x] Dev seed: one return per resting state + store-credit balances (`_seed_returns`).
- [x] Figma pass complete. Page `10 · Returns — Wizard & Seller Initiate` holds 21 frames: customer wizard (review/agree, code, resume banner), seller initiation, customer list/detail/store-credit/checkout toggle, seller queue/detail/window config, admin list/detail/hub tab/customer store-credit viewer, customer mobile set, and a States & rules frame.
- [x] Prod gate closed: `return_agreement` is now seeded by `app.db.seed_policies` from `policy_seed/return_agreement.md` (the deploy runs it), and `admin_list_policies` enumerates `PolicyKind` so an admin can revise it. Previously prod had no agreement and no UI to publish one, so every return failed `agreement_unavailable`.
- [ ] **Deploy note:** the migration sets `sellerprofile_service.return_window_days = 0` for every existing row, so returns stay off until each seller sets a window in Seller → Settings. Intended (D3), but it means the feature ships dark — decide whether to pre-set windows for launch sellers.
- [ ] Twilio ContentSids for the 5 new WhatsApp templates (`otp_return`, `return_initiated`, `return_confirmed`, `return_accepted`, `return_rejected`, `return_closed`) before `WHATSAPP_PROVIDER=twilio`.
- [x] Seller **initiate on a customer's behalf** now has a UI: `/seller/orders/[id]/return` (entry point on a delivered order) backed by `GET /sellers/me/returns/eligibility/{order_id}`.
- [ ] Admin initiate-on-behalf (`POST /admin/returns`) is still API-only — no admin screen.
- [ ] Seller in-app notifications cover only "customer confirmed a return"; closed/expired/withdrawn notify the customer only, and there is no seller *email* path for returns.
- [ ] Dev-seed return histories are single-hop and attribute every transition to the customer, so a `return_event` timeline shows a path the state machine would reject. No seeded example of a full-order return (delivery fee) or a credit reversal.
- [ ] Returns tables are absent from `_COUNT_MODELS`, so `verify_expected_counts` cannot catch a seeding regression.
- [x] Wizard no longer creates the return before the agreement: steps 1–3 are local state, `POST /returns` fires when the customer accepts. An unconfirmed return on the order now shows a Resume / Discard banner ahead of the eligibility check.
- [x] `ReturnTimeline` now decides the payment step two-phase: the customer's `settlement_choice` before acceptance (no amounts exist yet), `payment_amount > 0` after, so a reversal-absorbed return no longer shows a step that can never complete.
- [x] Concurrency covered by `tests/test_returns_concurrency.py` — `asyncio.gather` over the ASGI client yields real overlapping transactions (fresh session per request on a NullPool engine): double-accept settles once, accept-vs-withdraw cannot both win, racing creates cannot double-lock a line.
- [ ] Platform-fee treatment of returned orders is deliberately out of scope (D11) — fees stand as charged. Revisit post-MVP.

## Design / UI follow-ups
- [ ] Redraw PWA icons (`frontend/public/icons/icon-192x192.png`, `icon-512x512.png`, `icon-180x180.png`) + `frontend/src/app/favicon.ico` in brand green (deferred from the 2026-06-23 green recolor — code/CSS are green; raster assets are still saffron).
- [ ] A11y (pre-existing, unrelated to recolor): `--color-success` `#1eba9c` used as success *text* on white is ~2.45:1 (fails AA) and reads close to brand green; consider pointing success-text uses at the darker `#018260`.
