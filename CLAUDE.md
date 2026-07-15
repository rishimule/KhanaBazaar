<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Khana Bazaar

Multi-vendor hyperlocal e-commerce platform for the Indian market (Instacart-like model).
Admins curate a master product catalog. Sellers register, get admin-approved, run **one store** with **multiple services** (Grocery, Food, Pharmacy, etc.) and manage local inventory/pricing. Customers shop per-store and pay via UPI.

## Subagent routing (gemini-worker)

This project has a `gemini-worker` subagent that wraps the Antigravity CLI (`agy`, running the `Gemini 3.1 Pro (High)` model). It exists to preserve Claude context for planning, writing code, and reviewing diffs.

**Delegate to `gemini-worker` before:**
- Reading more than 3 files to answer a question
- Any codebase-wide search ("find every place we…", "list all usages of…")
- Summarizing any file longer than ~500 lines
- Reading generated code, large logs, large JSON/CSV, or vendored dependencies
- Answering "does this repo already have X?" questions

**Do NOT delegate (do it yourself):**
- Editing, creating, or deleting files
- Running tests, linters, or build commands
- Git operations
- Brainstorming, plan-writing, or spec refinement — plan quality depends on you reading the code directly
- Reviewing a diff against a plan
- Small reads (1–3 specific files you already know you need)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI 0.135+ (Python 3.12), Uvicorn ASGI |
| ORM / Migrations | SQLModel 0.0.37+ + Alembic (asyncpg driver) |
| Database | PostgreSQL 15 |
| Cache / Broker | Redis 7 (Celery 5.6+ for background tasks) |
| Search | Meilisearch v1.11 (Docker locally; on the deploy VM in prod) |
| Auth | Self-hosted email-OTP + JWT (PyJWT HS256). **No Firebase, no passwords.** |
| Email | `EMAIL_PROVIDER=console` (dev) or `resend` (prod, raw httpx call — no SDK) |
| Config | Pydantic-Settings (`.env` files) |
| Frontend | Next.js 16.1 (App Router), React 19.2, TypeScript 5 |
| Frontend styling | CSS Modules + design tokens in `frontend/src/styles/design-tokens.css` (no Tailwind) |
| PWA | `frontend/public/sw.js` + `manifest.json` (registered in `app/layout.tsx`) |
| Package mgmt | `uv` (backend), `npm` (frontend) |
| Linting/Types | Ruff + Mypy (backend), ESLint 9 + TypeScript (frontend) |
| Testing | Pytest + pytest-asyncio (backend). **No frontend tests.** |
| Deployment | Google Cloud (Cloud Run web+api + Cloud SQL Postgres + e2-small VM for worker/Redis/Meilisearch + Firebase Hosting); CI via GitHub Actions + WIF on merge to `main` (`deploy/gcp/`, `docs/gcp_deployment.md`) |

## Project Structure

```
backend/app/                          # FastAPI app (run commands from here)
  src/app/
    main.py                           # Uvicorn entrypoint
    __init__.py                       # FastAPI app instance, CORS, route mounting
    api/                              # Routers (see API Surface below)
    core/                             # config, security, otp, email, redis, celery_app, rate_limit, indian_states
    db/                               # async session factory, seed scripts
    models/                           # SQLModel tables (base, address, catalog, profile, commerce, store, seller)
    services/                         # Business logic: checkout, orders, order_emails, seller_services, inventory, profiles
    schemas/                          # Pydantic request/response models
    utils/                            # address helpers, indian_states
    worker.py                         # Celery task definitions
  migrations/                         # Alembic versions
  tests/                              # Pytest integration tests (separate khanabazaar_test DB)
  pyproject.toml
frontend/
  src/
    app/                              # Next.js App Router
      stores/[id]/                    # Instacart-style service/category/subcategory layout
      cart/, checkout/[storeId]/      # Per-store checkout flow
      account/                        # Customer dashboard (orders, settings)
      seller/                         # Seller dashboard (signup, inventory, orders) — DashboardLayout
      admin/                          # Admin dashboard (categories, products, sellers, orders) — DashboardLayout
    components/                       # Navbar, Footer, DashboardLayout, DataTable, Modal, ProductCard, orders/*
    lib/                              # api, AuthContext, CartContext, cart, localCart, remoteCart, orders, format-address
    types/index.ts                    # TS interfaces mirroring backend models
    styles/                           # design-tokens.css, globals.css
  public/                             # icons/, manifest.json, sw.js
docs/                                 # architecture, flows, local_setup, development_guide, gcp_deployment, seller_signup
docker-compose.yml                    # Postgres + Redis + Meilisearch (+ meilisearch-test under `--profile test`)
deploy/gcp/                           # GCP deploy: bootstrap.sh, VM compose, runbook (README.md)
```

## Essential Commands

### Infrastructure
```bash
docker-compose up -d                                          # Postgres + Redis + Meilisearch
```

### Backend (from `backend/app/`)
```bash
uv sync                                                       # Install deps
uv run alembic upgrade head                                   # Apply migrations
uv run alembic revision --autogenerate -m "description"       # Generate migration
uv run uvicorn app.main:app --reload                          # Dev server (port 8000)
uv run celery -A app.core.celery_app worker --loglevel=info   # Celery worker
uv run pytest -v                                              # Tests (needs khanabazaar_test DB)
uv run ruff check .                                           # Lint
uv run mypy .                                                 # Types
```

### Frontend (from `frontend/`)
```bash
npm install
npm run dev                                                   # Port 3000
npm run build
npm run lint
```

API docs: `http://localhost:8000/docs`. All routes prefixed `/api/v1` (`core/config.py:8`).

## RBAC Roles

Defined in `backend/app/src/app/models/base.py:8-11`: **Customer**, **Seller**, **Admin**.

Auth chain (`core/security.py`):
- `HTTPBearer` → `decode_access_token` → `get_current_user` (loads User by JWT `sub`)
- Role guards: `get_current_seller`, `get_current_admin`
- Public endpoints take only `Depends(get_db_session)` (no auth)

## API Surface

Mounted in `api/__init__.py`. All under `/api/v1`:

| Prefix | Module | Purpose |
|--------|--------|---------|
| `/auth` | `auth.py` | OTP request/verify, login, logout, me |
| `/catalog` | `catalog.py` | Languages, services, categories, subcategories, master products |
| `/stores` | `stores.py` | Store list/detail, inventory |
| `/sellers` | `sellers.py` | Seller register, profile, services, applications, status |
| `/customers` | `customers.py` | Customer profile, addresses |
| `/carts` | `carts.py` | Cart ops, server-side sync |
| `/orders` | `orders.py` | Create, list, detail, status |
| `/tasks` | `tasks.py` | Celery test endpoint |
| `/meta` | `meta.py` | Health, languages |
| `/search` | `search.py` | `/suggest` (dropdown), `/products` (results), `/products/{id}/stores` (compare), `/stores` (store-name), `/click` (analytics) |
| `/admin` | `admin_actions.py` | Per-seller hub (`/sellers/{id}`), activity log (`/sellers/{id}/activity`), order force-rewind, force-refund, delivery-address override |

Public: catalog reads, store reads, health, languages, **search**.
Seller-only: register, profile/services updates, applications.
Admin-only: create categories/products, approve seller applications, **per-seller supervisor** actions (`/admin/*`).

## Environment Variables

### Backend `backend/app/.env`
**Required**: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `OTP_PEPPER`
**Optional**:
- `ENVIRONMENT` (development/production)
- `COMPANY_NAME` (default `Khanabazaar`) — single source for the displayed brand name. `EMAIL_BRAND_NAME` and the OpenAPI `PROJECT_NAME` derive from it when unset (an explicit `EMAIL_BRAND_NAME`/`PROJECT_NAME` still overrides). Drives email + SMS + WhatsApp-mock copy. NOTE: production WhatsApp text comes from Twilio-approved templates, not this var. **Prod (GCP `khanabazaar-mvp`) is pinned to `Sarvaka`**: api via `--update-env-vars=COMPANY_NAME` in `deploy.yml`; the VM worker (order/delivery emails+SMS) via `COMPANY_NAME` in `/opt/kb/.env`.
- `EMAIL_PROVIDER` (`console` default | `resend`)
- `RESEND_API_KEY`, `RESEND_FROM_EMAIL` (only when `EMAIL_PROVIDER=resend`)
- `SUPPORT_EMAIL` (default `support@khanabazaar.example`) — destination inbox for `/customers/me/support` messages
- `SMS_PROVIDER` (`console` default | `twilio`)
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` (only when `SMS_PROVIDER=twilio`)
- `WHATSAPP_PROVIDER` (`none` default | `console` | `twilio`), `TWILIO_WHATSAPP_FROM` (`whatsapp:+...` sender; reuses `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`). Mock (`console`) captures to `dev_whatsapp` → `/dev-whatsapp`. Template-first: copy lives in `core/whatsapp_templates.py`; OTP is WhatsApp-preferred with SMS fallback (`core/otp_delivery.py`); customer order-status updates fire from `record_and_dispatch_notification` (best-effort, verified phone only). See `docs/superpowers/specs/2026-06-11-whatsapp-messaging-channel-design.md`.
- `DEV_INBOX_USER`, `DEV_INBOX_PASSWORD` — HTTP Basic creds for the dev-only `/dev-emails` + `/dev-sms` + `/dev-whatsapp` mailbox pages. Both must be set to enable the feature; `/api/v1/dev/*` endpoints `404` unless `ENVIRONMENT=development`. See `docs/superpowers/specs/2026-06-05-dev-mailbox-design.md`.
- `JWT_EXPIRES_HOURS` (default 24)
- `OTP_TTL_SECONDS`, `OTP_MAX_ATTEMPTS`, `OTP_RESEND_COOLDOWN`, `OTP_MAX_PER_HOUR`
- `FRONTEND_ORIGIN` (default `http://localhost:3000,http://127.0.0.1:3000`) — comma-separated CORS allow-list; parsed by `Settings.cors_origins` and passed to `CORSMiddleware`
- `GOOGLE_MAPS_SERVER_API_KEY` (server-only, IP-restricted in GCP — powers `/api/v1/geo/*`)
- `GOOGLE_MAPS_BROWSER_API_KEY` (referrer-restricted, exposed to FE as `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`)
- `GEO_RATE_LIMIT_PER_MIN` (default 30), `GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS` (60), `GEO_REVERSE_CACHE_TTL_SECONDS` (86400)
- `MEILI_URL` (default `http://localhost:7700`), `MEILI_MASTER_KEY` (default `dev-master-key-change-me` for dev)
- `SEARCH_RATE_LIMIT_SUGGEST_PER_MIN` (default 60), `SEARCH_RATE_LIMIT_PRODUCTS_PER_MIN` (default 30)
- `SEARCH_SUGGEST_CACHE_TTL_SECONDS` (default 60), `SEARCH_SERVICEABLE_GRID_TTL_SECONDS` (default 60)
- `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT` (Web Push; all optional — push is disabled/no-op when `VAPID_PRIVATE_KEY` is empty). `VAPID_PRIVATE_KEY` is the **raw base64url** EC private key (~43 chars), NOT a PKCS8 PEM — `pywebpush`'s `Vapid.from_string` base64url-decodes it to the 32-byte scalar and rejects a PEM (`ASN.1 parsing error`). Keygen in `docs/development_guide.md` §12.
- **Image storage**: `IMAGE_STORAGE_BACKEND` (`local` default | `gcs`), `IMAGE_MAX_UPLOAD_MB` (10), `IMAGE_MAX_DIMENSION_PX` (2048), `IMAGE_MAX_PIXELS` (40M decompression-bomb guard), `MEDIA_LOCAL_DIR` (`var/uploads`) + `MEDIA_URL_PREFIX` (`/media`) for the local backend. GCS backend: `GCS_PRODUCT_IMAGES_BUCKET` + optional `GCS_PUBLIC_BASE_URL` (catalog images), `GCS_USER_MEDIA_BUCKET` + optional `GCS_USER_MEDIA_PUBLIC_BASE_URL` (**dedicated** bucket for user avatars/future banners), `AVATAR_MAX_DIMENSION_PX` (512). Storage abstraction in `services/image_storage.py` (`get_image_storage(bucket=…)` + `get_user_media_storage()`); local backend shares one dir (key prefix separates `products/` vs `avatars/`). See `docs/gcp_deployment.md`.

### Frontend `frontend/.env.local`
- `NEXT_PUBLIC_API_URL` — backend base URL. Default `""` (empty). Empty means relative paths; Next.js `rewrites()` in `next.config.ts` proxies `/api/v1/:rest(.*)` to `http://localhost:8000`. Production overrides this with the absolute backend URL (inlined at build time).
- `NEXT_PUBLIC_COMPANY_NAME` (default `Khanabazaar`) — displayed brand name across all pages, titles, navbar/footer, login, and the PWA manifest (`src/app/manifest.ts`). **Inlined at build time** (rebuild to change). Code reads it via `src/lib/brand.ts`; i18n copy uses a `{brand}` token in `messages/*.json` (all 5 locales, native-script copy included) substituted at message-load time by `src/i18n/brand-messages.ts`. Avoid ICU-special chars (`{ } ' #`) in the value — they'd break next-intl parsing after interpolation. **Prod (GCP) builds with `Sarvaka`** via `--build-arg NEXT_PUBLIC_COMPANY_NAME` in `deploy.yml` (build-time inlining; the web Cloud Run service needs no runtime env for this).
- `NEXT_PUBLIC_VAPID_PUBLIC_KEY` — must equal the backend `VAPID_PUBLIC_KEY` (the browser's `applicationServerKey`).

## Testing

`backend/app/tests/conftest.py`:
- **Real Postgres test DB** (`khanabazaar_test`) — not SQLite, not mocked. Drop+recreate tables per function.
- Pre-seeds 5 languages (en, hi, mr, gu, pa) before each test.
- Auth dependencies overridden via `app.dependency_overrides` (see `test_stores.py` for pattern).
- Celery runs **eager mode** in tests (inline execution, no worker needed).
- Order-email dispatchers patched to no-op to avoid connection-pool races.

No frontend tests configured.

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/src/app/main.py` | Uvicorn entry |
| `backend/app/src/app/__init__.py` | App factory, CORS (env-driven via `FRONTEND_ORIGIN` → `settings.cors_origins`), router mount, search-index bootstrap on startup |
| `backend/app/src/app/core/config.py` | Pydantic Settings, `API_V1_STR="/api/v1"` |
| `backend/app/src/app/core/security.py` | JWT encode/decode, role guards |
| `backend/app/src/app/db/session.py` | Async session factory |
| `schema.sql` | Full Postgres schema snapshot — source of truth is the SQLModel models + Alembic; pinned to head `f6495e1b1c31`. Regenerate when the head changes. |
| `frontend/src/app/layout.tsx` | Root layout, mounts AuthProvider + CartProvider, registers PWA manifest |
| `frontend/src/lib/api.ts` | Typed fetch wrapper, `ApiError` class |
| `frontend/src/lib/AuthContext.tsx` | Auth state (token in `localStorage` key `kb_token`, OTP flow) |
| `frontend/src/lib/CartContext.tsx` | Cart state + localStorage persistence |
| `frontend/src/types/index.ts` | TS interfaces mirroring backend models |

## Non-obvious patterns / gotchas

**Multi-vendor model**: 1 Seller → 1 Store → many Services (Grocery, Food, Pharmacy, …). Each Service has Categories → Subcategories → MasterProducts. Inventory is per-product per-store.

**Catalog is multi-lingual**: `Service`, `Category`, `Subcategory`, `MasterProduct` all have `*Translation` tables keyed by `LanguageCode`. Pre-seeded languages: en, hi, mr, gu, pa.

**Product placeholder images**: dev seed assigns `MasterProduct.image_url` from `CATEGORY_IMAGE_POOLS` in `backend/app/src/app/db/_dev_seed_data.py` — 3 themed LoremFlickr URLs per category (`https://loremflickr.com/400/400/<keyword>?lock=<n>`), round-robin by index-within-subcategory. No local image files in `frontend/public/`. Anchor products in `dev_seed.py` get their URLs from a post-process loop that runs at module load before `PRODUCTS.extend(EXTRA_PRODUCTS)`. Adding a new category without a matching `_CATEGORY_IMAGE_KEYWORDS` entry crashes seed loud (`KeyError: no image pool registered`). ProductCard / ProductDetail render via raw `<img referrerPolicy="no-referrer">` (avoids leaking browse paths to the CDN) and fall back to a category-emoji glyph on load failure.

**Auth is email-OTP + JWT only**: No passwords, no Firebase. Endpoints: `POST /api/v1/auth/otp/request`, `POST /api/v1/auth/otp/verify`. **Seller signup uses a 4-OTP-endpoint chain**: `/auth/otp/request` → `/auth/seller/otp/verify` (returns 10-min `email_token`) → `/auth/seller/phone/otp/request` (gated by `email_token`, dispatches SMS) → `/auth/seller/phone/otp/verify` (returns 10-min `signup_token` binding email + verified phone) → `/auth/seller/register` (consumes `signup_token`, phone read from claims). OTP stored in Redis (TTL 600s default), rate-limited 5/hour per identifier, 60s resend cooldown. Email and phone OTPs share Redis primitives via a `namespace` argument (`otp:email:*` vs `otp:phone:*`). SMS provider switch in `core/sms.py` — `console` logs to stdout, `twilio` does direct httpx POST (no SDK dep). JWT issued on verify (`sub=user.id`, `role=user.role`, 24h TTL).

**Cart architecture (frontend)**:
- Guest carts: `localStorage` key `kb_carts` (JSON keyed by `(storeId, serviceId)` sub-baskets — one entry per store+service pair)
- Guest session ID: `localStorage` key `kb_session_id` (UUID, generated once)
- Logged-in users sync to backend via `POST /api/v1/carts/sync`
- Server `Cart` unique key is `(customer_profile_id, store_id, service_id)` — a single store can hold multiple sub-baskets (Grocery, Food, Pharmacy, …) for the same customer. Cross-service add auto-splits into a new sub-basket; no modal.

**Per-store-per-service checkout** (`services/checkout.py`, `app/checkout/[storeId]/page.tsx`): one Order per `(store, service)` sub-basket — sibling sub-baskets at the same store stay intact when one is placed. Customer picks delivery address + payment method per sub-basket. Inventory row-locked + validated, then Order (carrying `service_id` + `service_name_snapshot`) + OrderItems + Payment + Delivery created atomically. Catalog drift between add and checkout: admin re-parenting a subcategory to a different service → `409 service_mismatch` (`_assert_locked_inventory_matches_service`); seller revoking the service → `409 service_unavailable` (`_validate_service_active_for_store`). Both fire at checkout only — no auto cart purge, customer prunes the sub-basket. `Order` carries `service_id` (FK) + `service_name_snapshot` (string) so order emails and history can label which service the order is for even if the catalog changes later. `OrderStatus` enum: `pending → packed → dispatched → delivered` plus `cancelled` (and dormant `paid` value not currently transitioned to). **Delivery fee is per-`(store, service)`**: `SellerProfileService` carries `free_delivery_threshold` + `delivery_fee` (flat fee charged when cart subtotal is below the threshold; threshold 0 / fee 0 / no row = free). `services.checkout._compute_delivery_fee` computes it at checkout and writes `Order.delivery_fee`; **no minimum-order block** (any cart can check out). Order-placed emails show a subtotal/fee breakdown when fee > 0. Seller/admin set both per service (`PATCH /sellers/me|admin/{id}/services/{id}`, audit action `service.set_delivery_settings`). Tax still hardcoded to 0.

**Cart + order routes changed shape for service scoping**:
- `DELETE /api/v1/carts/{store_id}/{service_id}` — clear a single sub-basket (replaces the old `DELETE /api/v1/carts/{store_id}` which cleared every sub-basket at a store).
- `GET /api/v1/orders` — customer listing accepts optional `?service_id=` to filter to one service.

**Seller signup flow**: register (multi-step wizard) → status `pending` → admin approves → status `approved` → can manage store/inventory. `/seller/signup/pending` blocks dashboard until approval. See `docs/seller_signup.md`.

**Seller phone change requires OTP**: an Approved seller changing their phone via the identity change-request must first verify the NEW number through an authenticated OTP chain — `POST /sellers/me/phone/otp/request` → `/sellers/me/phone/otp/verify` (returns 10-min `phone_change_token` JWT, `type=seller_phone_change`, bound to `(user_id, normalized_phone)`; OTP namespace `seller_phone_change`). The CR `create`/`resubmit` endpoints carry `phone_change_token`; `services._require_phone_verification` requires it only when the proposed identity phone differs from the current one (name/business-only edits need no token). `IdentityPayload` normalizes the phone via `core.otp.normalize_phone` (strict `+91[6-9]XXXXXXXXX`) so the token/payload/stored values compare cleanly. Phone uniqueness is **seller-scope only** (`ix_sellerprofile_phone`) — a phone already on a customer/admin profile is allowed; only seller-vs-seller collisions raise `409 phone_taken` (checked at OTP-request, the gate, and `_apply_identity` approve-time as a TOCTOU backstop). Admin approve-with-edits bypasses seller OTP (admin authority). Spec: `docs/superpowers/specs/2026-05-30-seller-phone-change-otp-design.md`.

**Store detail page** (`app/stores/[id]/page.tsx`, commit `31e0cc0`): Instacart-style 3-pane — services sidebar → categories → products with per-store inventory.

**Email dispatch**: OTP and order emails sent via Celery tasks (`worker.py`). Provider switch in `core/email.py` — `console` logs to stdout, `resend` does direct httpx POST (no SDK dep). A temporary local-dev **Gmail SMTP** provider is also available — `EMAIL_PROVIDER=smtp` (send only) or `smtp+console` (send + `/dev-emails` capture); config via `SMTP_*` env vars (App Password required), `SmtpEmailSender`/`SmtpWithConsoleSender` in `core/email.py`. The `+console` composites tag the dev-mailbox `provider` column with the real transport (`smtp`/`resend`). **Two email paths honor `EMAIL_PROVIDER` independently**: the API request path via `get_email_sender()` (OTP request), and the Celery worker path via `worker._resolve_email` (order/notification/referral/support emails) — the latter has its own sync provider switch and bridges to `SmtpEmailSender` on a worker thread. Both were extended for SMTP.

**WhatsApp dispatch (template-first)**: Provider switch in `core/whatsapp.py` — `none` (disabled, `get_whatsapp_sender()` returns `None`) | `console` (mock → captures to `dev_whatsapp` table → `/dev-whatsapp`) | `twilio` (Content API, `whatsapp:`-prefixed numbers; ContentSids deferred to go-live). **Unlike SMS, callers never send free text** — WhatsApp business-initiated messages require pre-approved templates, so callers pass a registered template name + variables from the `core/whatsapp_templates.py` registry (`AUTHENTICATION` for OTP, `UTILITY` for order updates). OTP delivery routes through `core/otp_delivery.deliver_phone_otp` (WhatsApp-preferred, SMS-fallback on failure/disabled) at the 3 phone-OTP sites; customer login OTP is additionally mirrored to WhatsApp (best-effort, verified phone only). Customer order-status updates fire from `record_and_dispatch_notification` (outside its try/except, additive alongside email, verified-phone gate in the Celery task). `get_whatsapp_sender()` is `@lru_cache`d → tests toggling `WHATSAPP_PROVIDER` must `cache_clear()`. Spec: `docs/superpowers/specs/2026-06-11-whatsapp-messaging-channel-design.md`.

**Geo / PostGIS / DIGIPIN**: Address coordinates stored as `latitude`/`longitude` plus a Postgres-GENERATED `geo geography(Point, 4326) STORED` column with a GiST index — SQLModel does NOT declare `geo`; reads are raw SQL. `address.digipin` is auto-derived from lat/lng in `address_from_payload` via `app/utils/digipin.py` (India Post 4×4-grid algorithm, India bbox only). `Store` carries `delivery_radius_km` (default 5) and `pin_confirmed` (false until seller confirms map pin). Distance + filter via `GET /stores/?lat=&lng=&sort=distance` (PostGIS `ST_DWithin` + `ST_Distance`); order creation re-asserts `ST_DWithin` against the customer address. `/api/v1/geo/{autocomplete,place,reverse,serviceability}` proxies Google Maps server-side so the API key never reaches the browser; per-IP rate limit 30/min, Redis-cached. Local Postgres image: `postgis/postgis:15-3.4`. Alembic `migrations/env.py` skips PostGIS system tables AND the generated `geo` column during autogen — do not "clean up" those guards. Frontend: `<AddressAutocomplete>` + `<MapPicker>` (vis.gl/react-google-maps) used by `<AddressFields>`; `<DeliveryLocationContext>` persists guest location to `localStorage` (`kb_delivery_location`); navbar 'Deliver to' chip opens `<DeliveryLocationPicker>`. Browser key (`NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`) is referrer-restricted. See `docs/development_guide.md` §10 + `docs/superpowers/specs/2026-05-06-geo-stores-delivery-radius-design.md`.

**Frontend → backend path is a Next.js rewrite, not a direct fetch**: `NEXT_PUBLIC_API_URL` is empty in dev so the browser hits `/api/v1/*` on the current origin and `next.config.ts` proxies server-side to `http://localhost:8000`. Same-origin from the browser means no CORS, and same-origin under ngrok means the backend never has to be exposed publicly. **Use `:rest(.*)` in the rewrite source**, not `:path*` — `:path*` silently strips a trailing slash, FastAPI then 307s to the slashed URL using the upstream Host header (`https://localhost:8000`), which is unreachable from a phone. Also keep `skipTrailingSlashRedirect: true` so Next.js itself doesn't 308 the slash off before the rewrite. Mobile testing: `./scripts/dev.sh start --tunnel` brings up the stack plus an ngrok agent (config at `~/.config/ngrok/ngrok.yml`) forwarding `:3000`. See `docs/local_setup.md` §6a.

**Search (Meilisearch)**: Three indexes — `products`, `stores`, `search_terms`. All search proxies through `/api/v1/search/*`; **no browser-direct Meilisearch**. Sync via SQLAlchemy `after_commit` listeners in `app.search.hooks` → Celery tasks in `app.search.tasks` (each task takes Redis lock `meili_sync:product:<id>` for 5s to coalesce). PostGIS + Redis (500m grid, 60s TTL) drives serviceable-store filtering in `app.search.locality`. Bulk reindex: `uv run python -m app.search.reindex --all`. Settings + synonyms in `app.search.settings` and `app.search.synonyms.json`; bump `SETTINGS_VERSION` to re-push. Document-level fields are flat (`name_en`, `name_hi`, …) — adding a new locale requires extending `LanguageCode`, then rebuilding the products index. Async session in Celery tasks runs via a thread-bridged `asyncio.run` so eager-mode tests stay sane. p95 sync lag <2s; suggest cache TTL 60s in Redis.

**Notifications (Web Push + in-app feed)**: Customer order notifications have **two layers** — (1) a universal navbar bell backed by the `notification` table (`GET /api/v1/notifications`, works on every browser), and (2) best-effort Web Push (VAPID + `pywebpush`) for OS-level alerts delivered even when the app is closed. **Customers only** (sellers are a later phase; the `type` enum + push fan-out leave room). Five triggers fire `record_and_dispatch_notification` in `api/orders.py`: `pending` (placed, in `place_order`), `packed`/`dispatched`/`delivered` (`transition`), and `cancelled` (`cancel`, placed outside the role-based email branch so admin cancels still notify). Admin rewind/refund/address-override deliberately do **not** notify. The notification row + push are best-effort and never block the order path. iOS gets Web Push **only inside an installed PWA** (16.4+) — a Safari tab can't subscribe; the enable flow routes iOS users to the existing `IOSInstallSheet` via `usePWAInstall`. Opt-in is **per-device** (browser permission + subscription presence, not a server flag), surfaced in the navbar bell banner + account preferences, both driven by `usePushOptIn()`. Logout tears down the device subscription (shared-device safety). Push subscriptions returning 404/410 are pruned. **VAPID private key MUST be raw base64url (not PKCS8 PEM)** — `pywebpush`'s `Vapid.from_string` only accepts the base64url-decoded 32-byte scalar; a PEM string fails `ASN.1 parsing error: invalid length` and every push silently errors. **`VAPID_SUBJECT` must be a real deliverable contact** (real `mailto:` domain or real `https:` URL) — Apple rejects placeholder/`.example` domains with `403 BadJwtToken` (FCM is lenient, so it only bites Safari/Apple). The client (`subscribeToPush`) compares the existing subscription's `applicationServerKey` and re-subscribes if the VAPID key rotated (a sub is permanently bound to the key it was created with; signing with a different key → `403 BadJwtToken`). Tests: `dispatch_notification_push` is patched to no-op in `conftest._patch_email_dispatch` so the notification row is asserted without a real dev-DB push connection. Notification copy is **English-only** for now.

**i18n routing — register new non-localized top-level routes**: customer routes carry a locale URL prefix via `next-intl` (`frontend/src/middleware.ts`). Operator/dev pages (`/seller`, `/admin`, `/dev-logs`, `/dev-emails`, `/dev-sms`, `/dev-whatsapp`) must opt OUT by being listed in `frontend/src/i18n/unsupported-routes.ts` (`I18N_UNSUPPORTED_PREFIXES` **and** one of `COOKIE_LOCALE_PREFIXES`/`NO_LOCALE_PREFIXES` per the invariant). **A new top-level page NOT in that list is routed through next-intl and 404s** even though it builds + prerenders fine (the page file, manifests, and image are all correct — the middleware just never lets the request reach it). This bit `/dev-whatsapp` on first deploy.

**Language preference — one source of truth, URL-driven storefront**: `User.preferred_language` (backend) is the single source of truth — read by `/auth/me` (locale seeding), the worker (order/notification copy), and the customer profile response. `CustomerProfile.preferred_language` is a vestigial mirror (only written by `PATCH /customers/me/preferences`, no longer authoritative for reads). Every explicit language change persists to `User` via `PATCH /auth/me/language` (operator switcher + `LanguagePreferenceCard`) or `PATCH /customers/me/preferences` (account page, which mirrors onto `User`). **Storefront locale is fully URL-driven** — `localeDetection: false` in `i18n/routing.ts` (no browser `Accept-Language` auto-detect), `localePrefix: "as-needed"` so `en` is the unprefixed default and other locales are `/hi`, `/mr`, … Users opt into a locale via the switcher (moves the URL) and a logged-in customer's saved preference is applied by `<CustomerLocaleEnforcer>` (redirects the URL, no cookie). `api.ts` `resolveLocale` derives the browser locale from the **URL prefix** (customer) so catalog `Accept-Language` matches the page. **Why URL-driven, not cookie-driven:** the prod custom domain is Firebase Hosting → Cloud Run rewrite, and Firebase strips every request cookie except `__session` before it reaches the origin — so any cookie-based locale (next-intl's `NEXT_LOCALE`, or middleware `Accept-Language` detection) never reaches the Next.js server on prod. **Operators are the exception:** operator routes are non-localized (no URL locale), so the dashboard locale lives in a cookie read by `(operator)/layout.tsx` + `api.ts` on operator routes. That cookie is named **`__session`** (`OPERATOR_LOCALE_COOKIE` in `frontend/src/lib/localeCookies.ts`) *specifically because Firebase Hosting forwards only `__session` to the origin* — so the operator dashboard locale works on the prod domain, not just locally / on the direct Cloud Run URL. The value is a bare locale code, validated against `routing.locales` on read (falls back to English if `__session` is ever repurposed). It's still isolated from the storefront's `NEXT_LOCALE`, so storefront browsing can't clobber it. Logout clears both cookies (shared-device safety). See `frontend/src/lib/{operatorLocale,localeCookies}.ts` + `AuthContext.tsx`.

**CSS conventions**: Design tokens (CSS custom properties) in `frontend/src/styles/design-tokens.css`. Global utility classes (`btn`, `btn-primary`, etc.) in `frontend/src/app/globals.css`. Component scoping via `*.module.css`. **Never add Tailwind.**

**Async DB everywhere**: All routes use async sessions (`get_db_session`). When writing services, use `await session.exec(...)`, `await session.commit()`, `await session.refresh(obj)`.

**Admin seller supervisor + audit log**: Admins can act on a single seller's products and orders through `/admin/sellers/[id]/{profile,products,orders,activity}` (frontend) → `/api/v1/admin/*` + reused `/stores/{id}/inventory/*` and `/orders/{id}/{cancel,transition}` endpoints. Service functions accept `acting_admin_id: int | None = None`; when set, `admin_audit.log()` is called and the audit row commits in the **same transaction** as the mutation (no post-commit logging — rollback is atomic). Audit data lives in `admin_action_log` (new table, no FKs on `target_id` so deleted-row history survives). Admin order-mutating routes also enqueue `send_admin_order_action_email` Celery task to notify the seller. Admin writes against non-Approved sellers reject with `409 seller_not_active`. Frontend uses an `<ImpersonationBanner>` ("acting" vs "viewing" copy) + reason-required modal for destructive actions. See `docs/superpowers/specs/2026-05-16-admin-seller-supervisor-design.md`.

## Frontend Design Workflow (Figma-first)

**Every change to the web-app frontend MUST be designed in Figma before it is implemented in code.** The Figma file is the source of truth for the visual design and must stay accurate to the shipped UI at all times.

- **Figma file**: `Khana Bazaar — Web App Screens` (`https://www.figma.com/design/xE7k2Kll3aXDornOut63gC/Khana-Bazaar-%E2%80%94-Web-App-Screens`, file key `xE7k2Kll3aXDornOut63gC`). Existing screens: all 108 KB screens (customer/seller/admin × desktop + mobile) — see the `project_figma_screens.md` memory for component IDs + coordinate conventions.
- **Order of operations** for any new or changed frontend UI (new page, redesign, component tweak, layout/style change):
  1. Design the change in Figma first (use the `figma-generate-design` / `figma-use` skills; load the mandatory skill before any `use_figma` call).
  2. Get the Figma design correct — new screens added, changed screens updated to match the intended result.
  3. **Only then** implement the change in the Next.js code so the code matches the approved Figma design.
- **Keep them in sync**: when the code changes, the Figma file must be updated in the same effort so it never drifts from what's live. Treat an out-of-date Figma screen as a bug.
- **Scope**: applies to `frontend/` UI work. Pure backend, config, docs, or non-visual refactors (no rendered-output change) do not need a Figma pass.

## Git & GitHub Workflow

- **Never commit to `main`**. Always branch: `feat/`, `fix/`, `chore/`, `docs/`, `refactor/`, `test/`.
- **Conventional Commits**: `<type>(<scope>): <summary>` — imperative, ≤72 chars, no trailing period.
- **No AI co-author trailers** in commits/PRs.
- **Wait for explicit user approval before opening PRs**. Use `gh pr create` only.
- **Keep merged branches** — do not pass `--delete-branch`.
- All PRs: target `main`, must pass CI (Ruff + Mypy advisory — Pytest is intentionally **not** in CI; run the full suite locally with `uv run pytest -q` before merging), **merge-commit** (`gh pr merge --merge`) — no squash, no rebase.
- Always use `gh` CLI for GitHub ops (`gh pr create/list/merge`, `gh issue *`, `gh run list`). Never raw `git push` + manual PR.
- **After merging a PR**: `git checkout main && git pull` to sync local with remote. Always land back on `main` before starting next task.

**Forbidden**: `git push --force` on shared branches, `--amend` on pushed commits, committing `.env`/secrets, `--no-verify`, direct commits to `main`.

## Additional Documentation

- `docs/architecture.md` — system topology, tech stack rationale, data model diagram
- `docs/flows.md` — guest cart, auth, cart sync, per-store checkout, order fulfillment, seller signup, catalog, inventory
- `docs/local_setup.md` — Docker + backend + frontend setup
- `docs/development_guide.md` — env vars, Alembic workflow, OTP/JWT, Celery, testing patterns, frontend conventions
- `docs/gcp_deployment.md` — GCP deployment architecture (Cloud Run + Cloud SQL + VM + Firebase Hosting); runbook in `deploy/gcp/README.md`
- `docs/seller_signup.md` — seller registration wizard, OTP 2-step flow, admin verify, layout guard
- `docs/google_maps_setup.md` — provision the server + browser API keys for the maps feature, restrictions, env wiring, cost orientation
- `.claude/docs/architectural_patterns.md` — DI, model hierarchy, auth chain (any Firebase mention is stale)
- `TODO.md` — Phase tracker (Phases 1–4 complete, Phase 5 deployment in progress)

**Known TODOs surfaced during doc rewrite**:
- `OrderStatus.Paid` defined but never assigned by state machine; `Payment.status` flips to `paid` only on `delivered`.
- OpenTelemetry / Cloud Trace not yet wired in `app/__init__.py` — noted as a real-launch item in `docs/gcp_deployment.md`.
