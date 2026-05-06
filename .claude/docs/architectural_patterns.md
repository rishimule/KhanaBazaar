# Architectural Patterns & Conventions

Reference for the recurring patterns in the KhanaBazaar codebase. When adding new features, mirror these patterns rather than inventing new ones.

> Auth is **email-OTP + JWT (HS256)**. Any older mention of Firebase is stale and has been removed from the system.

---

## Backend

### 1. Auth dependency chain (FastAPI `Depends`)

All authenticated requests flow through composable dependencies in `backend/app/src/app/core/security.py`.

**Chain:** `HTTPBearer` → `verify_access_token` → `get_current_user` → role guard.

- `HTTPBearer(auto_error=False)` (`security.py:13`) — extracts the bearer token without auto-failing, so `verify_access_token` can return a uniform 401 with the `WWW-Authenticate` header.
- `decode_access_token` (`security.py:27`) — `jwt.decode` with `HS256` and `settings.JWT_SECRET`. Raises 401 on `ExpiredSignatureError` / `InvalidTokenError`.
- `verify_access_token` (`security.py:44`) — wraps `decode_access_token` and rejects missing credentials.
- `get_current_user` (`security.py:56`) — resolves the JWT `sub` claim to a `User` row; rejects missing or inactive users.
- Role guards: `get_current_customer` (`security.py:77`), `get_current_seller` (`security.py:86`, also accepts Admin), `get_current_admin` (`security.py:95`).

Endpoints declare access by injection:
- **Public:** only `Depends(get_db_session)` (e.g. catalog reads, store reads, `/meta`).
- **Customer:** `Depends(get_current_customer)`.
- **Seller:** `Depends(get_current_seller)`.
- **Admin:** `Depends(get_current_admin)`.

### 2. Email-OTP flow (Redis-backed) and 2-step seller variant

OTP logic lives in `backend/app/src/app/core/otp.py`. Codes are hashed with a peppered SHA-256 and stored in Redis.

- `request_otp(email, redis)` (`otp.py:52`) — checks the resend cooldown key, increments the hourly counter, generates a 6-digit code, and writes hash + `attempts=0` to `otp:code:{email}` with `OTP_TTL_SECONDS` TTL. Pipeline-atomic.
- `verify_otp(email, code, redis)` (`otp.py:74`) — constant-time HMAC compare on the hash; increments `attempts` on miss; deletes the key once `OTP_MAX_ATTEMPTS` is hit. **Does not delete the key on success** — the caller must call `consume_otp_key`.
- `consume_otp_key` (`otp.py:95`) — final cleanup of code key + cooldown + hourly counters after a successful auth path commits.

Rate limit defaults (configurable in `core/config.py`): TTL 600s, max attempts 5, resend cooldown 60s, max per hour 5.

**2-step seller signup** uses short-lived JWTs in `security.py`:
- `create_email_verification_token(email)` (`security.py:104`) — issues a JWT with `type=seller_otp`, 10 min expiry. Returned by `/auth/seller/otp/verify`.
- `decode_email_verification_token(token)` (`security.py:115`) — validates the `type` claim and returns the email. Consumed by `/auth/seller/register` to create the seller user.

### 3. SQLModel three-tier model hierarchy

All tables in `backend/app/src/app/models/` follow the same shape, rooted in `models/base.py`:

1. **`BaseSchema`** (`base.py:14`) — `id`, timezone-aware UTC `created_at`, `updated_at`. Not a table itself.
2. **`*Base` mixin** (e.g. `UserBase` at `base.py:26`) — domain fields without `table=True`. Reusable for read/write schemas if needed.
3. **Table model** (e.g. `User` at `base.py:34`) — combines `BaseSchema + *Base` with `table=True`.

`UserRole` (`base.py:8`) is a string enum: `Customer`, `Seller`, `Admin`. `User.hashed_password` is nullable and unused (email-OTP only) — kept as a column for future password support.

The same three-tier pattern is applied across `catalog.py`, `store.py`, `commerce.py`, `profile.py`, `address.py`, `seller.py`.

### 4. Multi-lingual catalog via translation tables

`backend/app/src/app/models/catalog.py` defines parallel `*Translation` tables for every catalog entity:

- `Service` (`catalog.py:24`) ↔ `ServiceTranslation` (`catalog.py:31`)
- `Category` (`catalog.py:40`) ↔ `CategoryTranslation` (`catalog.py:49`)
- `Subcategory` (`catalog.py:58`) ↔ `SubcategoryTranslation` (`catalog.py:65`)
- `MasterProduct` (`catalog.py:74`) ↔ `MasterProductTranslation` (`catalog.py:81`)

Translation rows are unique on `(entity_id, language_code)` and `language_code` foreign-keys to `Language.code`. Pre-seeded languages (in `LanguageCode` at `catalog.py:9`): `en, hi, mr, gu, pa`.

The frontend sends `Accept-Language`; backend localizers read that header to pick a translation row. **No fallback locale strategy** — endpoints either match the requested language or fall back per-call to English/slug (e.g. `_snapshot_product_names` at `services/checkout.py:167`).

### 5. Router registration (one file per domain)

Routers live in `backend/app/src/app/api/`, one file per domain. Each defines `router = APIRouter()` and is registered in `api/__init__.py:1-25`:

| Prefix | Module |
|--------|--------|
| `/auth` | `auth.py` |
| `/catalog` | `catalog.py` |
| `/stores` | `stores.py` |
| `/sellers` | `sellers.py` |
| `/customers` | `customers.py` |
| `/carts` | `carts.py` |
| `/orders` | `orders.py` |
| `/tasks` | `tasks.py` |
| `/meta` | `meta.py` |

`api_router` is mounted by the FastAPI app under `settings.API_V1_STR` (`/api/v1`). To add a domain: create `api/<domain>.py` exporting `router`, then add a single `include_router(...)` line in `api/__init__.py`.

### 6. Async DB session per request

`backend/app/src/app/db/session.py` defines a single async engine and a request-scoped session factory:

- `engine = create_async_engine(settings.DATABASE_URL, echo=True, future=True)` (`session.py:8`) — asyncpg under SQLAlchemy. **`echo=True` is dev-only** and should be disabled in production deployments.
- `get_db_session` (`session.py:14`) — async generator yielding `AsyncSession(engine, expire_on_commit=False)`. `expire_on_commit=False` is required so committed instances stay readable for response serialization.

All endpoints use `await session.exec(...)`, `await session.commit()`, `await session.refresh(obj)`. Never call sync SQLModel methods.

### 7. Atomic per-store checkout with row-locked inventory

`backend/app/src/app/services/checkout.py` exposes `place_order_for_store` (`checkout.py:192`). It composes:

1. `_resolve_address` (`checkout.py:121`) — verifies the address is owned by the customer; both 404 and 403 use `detail="invalid_address"` so callers cannot distinguish.
2. `_load_cart_for_store` (`checkout.py:142`) — loads `(Cart, [CartItem])` for `(customer, store)`; raises `cart_not_found` / `cart_empty`.
3. `lock_inventory_rows` (in `services/inventory.py`) — `SELECT ... FOR UPDATE` on every involved `StoreInventory` row.
4. `_validate_inventory_availability` (`checkout.py:44`) — pure function; raises 409 `item_unavailable` / `insufficient_stock`.
5. `_validate_stores_active` (`checkout.py:66`) — not row-locked on purpose; an admin race correctly produces 409 + rolls back the inventory locks.
6. `_snapshot_product_names` (`checkout.py:167`) — joins `MasterProductTranslation` (en) with fallback to `MasterProduct.slug`.
7. `_build_order_for_cart` (`checkout.py:80`) — pure builder returning `(Order, [OrderItem], Payment, Delivery)`. Decrements stock via the locked ORM instances; unit-of-work flushes while the row lock is held.
8. Cart rows are deleted (items first for FK), then `await session.commit()` + `refresh`.

MVP constants `MVP_DELIVERY_FEE = 0.0` and `MVP_TAX = 0.0` (`checkout.py:29-30`). Edit here so every order built by this service stays in sync.

### 8. Celery + email provider switch

- `backend/app/src/app/core/celery_app.py` — `Celery("khanabazaar")` using `settings.REDIS_URL` for both broker and backend; JSON serializer; UTC.
- `backend/app/src/app/core/email.py` — `EmailSender` Protocol with two implementations:
  - `ConsoleEmailSender` (`email.py:16`) — logs + prints to stdout. Default.
  - `ResendEmailSender` (`email.py:22`) — direct `httpx.AsyncClient` POST to `https://api.resend.com/emails`. **No Resend SDK dependency.**
  - `get_email_sender()` (`email.py:40`) — `lru_cache`'d switch on `settings.EMAIL_PROVIDER`.
- `backend/app/src/app/worker.py` — Celery task definitions (`send_otp_email_async`, order/seller email tasks). Sync wrappers spawn a thread + new event loop for async DB lookups so they work both under a real worker and under EAGER tests.

### 9. Test fixtures: real Postgres, eager Celery, dependency overrides

`backend/app/tests/conftest.py`:

- **Real Postgres test DB** at `postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar_test` (`conftest.py:25`). Not SQLite, not mocked.
- `_reset_schema` (`conftest.py:35`) — drops/recreates `public` schema (not just `metadata.drop_all`). Required because SQLModel does not drop Postgres enum types, which would collide on the next `create_all` with `pg_type_typname_nsp_index`.
- `setup_test_db` autouse fixture (`conftest.py:45`) — runs `_reset_schema` + `create_all` and seeds the 5 languages **before each test function**.
- `os.environ["CELERY_TASK_ALWAYS_EAGER"]` set before importing `celery_app` (`conftest.py:15`); also sets `task_always_eager=True` and `task_eager_propagates=True` on the imported app (`conftest.py:21-22`). Tests run Celery tasks inline.
- `app.dependency_overrides[get_db_session] = override_get_db_session` (`conftest.py:70`) — global override using a fresh test-DB session.
- `_patch_email_dispatch` autouse fixture (`conftest.py:83`) — no-ops `dispatch_order_placed`, `dispatch_order_status_changed`, `dispatch_seller_approved`, `dispatch_seller_rejected` for every test **except** `test_order_emails`. The real dispatchers spawn a thread + open an engine to the dev DB; in EAGER mode that races with the test loop's pool.
- Per-test-file fixtures override role guards (e.g. `get_current_admin`, `get_current_seller`) with mock `User` objects, then pop the override on teardown.

---

## Frontend

### 10. CSS Modules + design tokens (no Tailwind)

- **Design tokens** in `frontend/src/styles/design-tokens.css` — colors, typography, spacing, shadows, durations, easing, z-index.
- **Global utility classes** (`btn`, `btn-primary`, `btn-secondary`, resets) in `frontend/src/app/globals.css`.
- **Component scoping** via co-located `*.module.css` files; components import `import styles from "./Component.module.css"` and apply via `className={styles.foo}`.

**Never add Tailwind.** New colors / spacing must go into `design-tokens.css` so the system stays a single source of truth.

### 11. Two-layer cart (local + remote, bridged in context)

Cart state spans three modules:

1. **Persistence (guest):** `frontend/src/lib/localCart.ts` — pure functions over `localStorage`:
   - `kb_carts` — JSON map `storeId → Cart`. One cart per store.
   - `kb_session_id` — UUID generated once per browser; identifies guests for backend sync.
2. **Persistence (authenticated):** `frontend/src/lib/remoteCart.ts` — typed wrappers over `/api/v1/carts/*` endpoints (`listCarts`, `addItem`, `updateItemQty`, `removeItem`, `clearStoreCart`, `syncCarts`).
3. **React layer:** `frontend/src/lib/CartContext.tsx`. `CartProvider` (`CartContext.tsx:39`) decides per render whether the user is a logged-in customer (`isCustomer`, `CartContext.tsx:64`) and routes ops to local vs. remote.

**Sync-on-login:** `lastSyncedUserId` ref (`CartContext.tsx:43`) ensures that when a customer first appears (`dbUser.id` differs from the ref), local carts are POSTed to `/api/v1/carts/sync` and `localCart.clearAllCarts()` runs on success (`CartContext.tsx:88-103`). Logout resets the ref (`CartContext.tsx:48-52`) so the next login does not see stale state from a previous account in the same tab.

**Optimistic updates:** mutating ops (`addItem`, `removeItem`, `updateQty`, `clearStoreCart`) snapshot `previous`, mutate state, hit the API, and roll back on error.

### 12. AuthContext: token in `localStorage`, OTP flow, role hook

`frontend/src/lib/AuthContext.tsx`:

- Token storage key: `kb_token` (`AuthContext.tsx:28`).
- `loading` initialises `true` only when a token exists, so first paint for guests does not flash a spinner (`AuthContext.tsx:33-36`).
- On mount, hydrates by calling `GET /api/v1/auth/me`; clears the token on 401 (`AuthContext.tsx:38-62`).
- `requestOtp(email)` (`AuthContext.tsx:64`) — POST `/api/v1/auth/otp/request`. Surfaces the structured `rate_limited` error with `retry_after`.
- `verifyOtp(email, code, fullName?)` (`AuthContext.tsx:82`) — POST `/api/v1/auth/otp/verify`. Two-phase: first call may return `{ user: null, needsName: true }` for new customers; the UI then re-calls with `fullName` to finish signup.
- `useRequireRole(role)` (`AuthContext.tsx:136`) — auth guard returning `{ authorized, loading, user, role }`. Used by seller/admin/customer layouts to gate sidebars + redirect.

### 13. Shared `DashboardLayout` (seller / admin / customer)

`frontend/src/components/DashboardLayout.tsx` is the single layout shell for all dashboards:

- Props: `{ role: "seller" | "admin" | "customer", roleName, title, navItems, children }`.
- Provides sidebar + mobile toggle + content area. Role-specific icon/colour via `ROLE_ICONS` / `ROLE_ICON_CLASSES` lookup tables (`DashboardLayout.tsx:31-41`).
- i18n via `useTranslations("Dashboard")` (`next-intl`).

The component is purely presentational. **Auth/role guards live in each `app/.../layout.tsx`**, where `useAuth()` / `useRequireRole()` redirect unauthorised users before `DashboardLayout` renders.

### 14. TypeScript types mirror backend models

`frontend/src/types/index.ts` declares interfaces (`User`, `Service`, `Category`, `Subcategory`, `MasterProduct`, `Store`, `Cart`, `CartItem`, `Order`, etc.) that map to backend SQLModel tables and response payloads.

Types are **manually maintained, not auto-generated**. When you change a SQLModel field, update this file in the same PR. Some fields are intentionally composed (`full_name`, `category_name`, `base_price`) because the API flattens joined data — frontend types reflect the wire shape, not raw DB rows.

### 15. API client with `ApiError` + locale-aware `Accept-Language`

`frontend/src/lib/api.ts`:

- Base URL from `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`, `api.ts:13`).
- Typed wrappers: `get<T>`, `post<T>`, `put<T>`, `patch<T>`, `del<T>`. Each accepts an optional `token` and attaches `Authorization: Bearer ...` when present (`api.ts:84-86`).
- `handleResponse` (`api.ts:31`) — throws `ApiError(detail, status)` on non-ok; returns `undefined` for 204 / empty body.
- `resolveLocale` (`api.ts:48`) — RSC path uses `next-intl/server.getLocale()`, falling back to the `NEXT_LOCALE` cookie via `next/headers`. Browser path reads the cookie directly. Final fallback: `"en"`. The resolved locale is sent as `Accept-Language` on every request.

Do not bypass these wrappers. Direct `fetch` calls miss the locale header and the structured error class.

### 16. PWA shell

- `frontend/public/manifest.json` — app name, icons (192/512 maskable), `theme_color`, `display: standalone`.
- `frontend/public/sw.js` — basic offline shell (network-first for navigations, cache-first for static assets). **Does not cache API responses**; treat it as offline navigation only.
- Registered in the operator and customer root layouts (`app/(operator)/layout.tsx`, `app/(customer)/[locale]/layout.tsx`) via the manifest `<link>` and a small registration script.

---

## Cross-cutting conventions

- **Multi-vendor model:** 1 Seller → 1 Store → many Services → Categories → Subcategories → MasterProducts. Inventory is per (`product`, `store`).
- **Per-store cart isolation:** no cross-store bundling. Each store has its own `Cart` and its own checkout flow.
- **Auth is JWT-only:** there are no sessions, no cookies for auth, no Firebase. The token in `localStorage` (`kb_token`) plus `Authorization: Bearer` is the entire auth surface.
- **All DB code is async:** routes, services, fixtures. Mixing sync SQLModel calls into the async stack will deadlock under load.
- **Email dispatch is always async via Celery** in production; tests run it eagerly in-process. Never call `EmailSender.send` directly from a request handler.
