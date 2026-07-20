<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Development Guide

How we develop on Khana Bazaar day-to-day. Covers env config, Alembic, OTP auth, Celery, tests, lint/types, frontend conventions, and the gotchas that bite us most often.

For one-time setup of Postgres / Redis / dependencies, see [`local_setup.md`](./local_setup.md). For deployment, see [`gcp_deployment.md`](./gcp_deployment.md). For Google Maps API keys (powering autocomplete + map pin + reverse geocoding), see [`google_maps_setup.md`](./google_maps_setup.md).

---

## 1. Environment configuration

### Backend `.env`

Lives at `backend/app/.env`. Template is `backend/app/.env.example`. Loader is the Pydantic `Settings` class in `backend/app/src/app/core/config.py`.

**Required**

| Var | Notes |
|---|---|
| `DATABASE_URL` | Must use the `postgresql+asyncpg://` driver. Plain `postgresql://` and `postgres://` are auto-rewritten by the validator, but write asyncpg explicitly to avoid surprises. |
| `REDIS_URL` | Used for both Celery broker and OTP storage. |
| `JWT_SECRET` | HS256 signing key. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `OTP_PEPPER` | HMAC pepper for OTP hashing. Generate with `python -c "import secrets; print(secrets.token_hex(16))"`. |

**Optional (with defaults)**

| Var | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | Free-form tag, used for log/diagnostic context. |
| `EMAIL_PROVIDER` | `console` | `console` prints OTPs to stdout. `resend` sends real email via raw httpx call. `smtp` / `smtp+console` send via SMTP (Gmail, local-dev only — see below). |
| `RESEND_API_KEY` | `""` | Required when `EMAIL_PROVIDER=resend`. |
| `RESEND_FROM_EMAIL` | `""` | Required when `EMAIL_PROVIDER=resend`. |
| `SMTP_HOST` | `""` | SMTP server host, e.g. `smtp.gmail.com`. Required when `EMAIL_PROVIDER=smtp`/`smtp+console`. |
| `SMTP_PORT` | `587` | `587` = STARTTLS, `465` = implicit SSL. |
| `SMTP_USERNAME` | `""` | SMTP login (the Gmail address). |
| `SMTP_PASSWORD` | `""` | 16-char Gmail App Password (NOT the account password). Secret — `.env` only. |
| `SMTP_FROM_EMAIL` | `""` | From address — must equal `SMTP_USERNAME` or a verified "Send mail as" alias, else Gmail rewrites `From`. |
| `SMTP_USE_TLS` | `false` | `true` → implicit SSL (port 465); `false` → STARTTLS (port 587). |
| `SMTP_TIMEOUT` | `10.0` | Seconds bounding the connect→STARTTLS→auth→send→quit handshake. |
| `SUPPORT_EMAIL` | `support@khanabazaar.example` | Destination inbox for `/customers/me/support` messages. Override per environment. |
| `SMS_PROVIDER` | `console` | `console` logs codes to stdout. `twilio` does direct httpx POST (no SDK). Drives seller phone-OTP step. |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | `""` | Required when `SMS_PROVIDER=twilio`. `TWILIO_FROM_NUMBER` is E.164 (e.g. `+15005550006`). |
| `WHATSAPP_PROVIDER` | `none` | `none` disables WhatsApp (`get_whatsapp_sender()` → `None`). `console` mocks → captures to `dev_whatsapp` → `/dev-whatsapp`. `twilio` uses the Content API. Set `console` in dev to see captures. |
| `TWILIO_WHATSAPP_FROM` | `""` | The `whatsapp:+...` sender (sandbox or approved number). Required when `WHATSAPP_PROVIDER=twilio`; reuses `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`. |
| `JWT_EXPIRES_HOURS` | `24` | Retired for the access token — no longer read for that TTL. Its 24h value now lives in `SESSION_UNTRUSTED_TTL_HOURS` (see below). |
| `ACCESS_TOKEN_TTL_MINUTES` | `15` | Access-token TTL. The access token is short-lived by design; long-term sign-in is handled by the rotating refresh-session system (see `docs/superpowers/specs/2026-07-17-trusted-device-long-term-signin-design.md`). |
| `SESSION_UNTRUSTED_TTL_HOURS` | `24` | Absolute cap for an untrusted (no "remember me") refresh session. |
| `SESSION_CUSTOMER_IDLE_DAYS` / `SESSION_CUSTOMER_MAX_DAYS` | `30` / `180` | Trusted-session sliding idle timeout / absolute cap for Customers. |
| `SESSION_SELLER_IDLE_DAYS` / `SESSION_SELLER_MAX_DAYS` | `14` / `90` | Trusted-session sliding idle timeout / absolute cap for Sellers. |
| `SESSION_ADMIN_IDLE_DAYS` / `SESSION_ADMIN_MAX_DAYS` | `7` / `30` | Trusted-session sliding idle timeout / absolute cap for Admins. |
| `REFRESH_TOKEN_REUSE_GRACE_SECONDS` | `30` | Window in which replaying the immediately-previous refresh token is tolerated (concurrent requests), rather than treated as theft. |
| `SESSION_REUSE_HISTORY_SIZE` | `5` | Bounded count of older rotated-out token hashes kept per session so reuse of a stale-but-genuine token (beyond just the immediate previous one) is still detected as a compromise signal. |
| `OTP_TTL_SECONDS` | `600` | OTP code lifetime in Redis. |
| `OTP_MAX_ATTEMPTS` | `5` | Verify failures before key is purged. |
| `OTP_RESEND_COOLDOWN` | `60` | Seconds between OTP requests for one email. |
| `OTP_MAX_PER_HOUR` | `5` | Hourly OTP request cap per email. |
| `FRONTEND_ORIGIN` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated CORS allow-list. Exposed via `Settings.cors_origins` and fed to `CORSMiddleware`. Override for staging/prod with the public frontend URLs. |
| `GOOGLE_MAPS_SERVER_API_KEY` | `""` | Required for `/api/v1/geo/*`. Server-only, IP-restricted in GCP console. |
| `GOOGLE_MAPS_BROWSER_API_KEY` | `""` | Referrer-restricted; exposed to the frontend as `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY` at build time. |
| `GEO_RATE_LIMIT_PER_MIN` | `30` | Per-IP rate limit on `/geo/*`. |
| `GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS` | `60` | Redis TTL for autocomplete cache. |
| `GEO_REVERSE_CACHE_TTL_SECONDS` | `86400` | Redis TTL for reverse-geocode cache (24 h). |
| `MEILI_URL` | `http://localhost:7700` | Meilisearch HTTP endpoint. |
| `MEILI_MASTER_KEY` | `dev-master-key-change-me` | Master key. Change for non-dev environments. |
| `SEARCH_RATE_LIMIT_SUGGEST_PER_MIN` | `60` | Per-IP rate limit on `/search/suggest`. |
| `SEARCH_RATE_LIMIT_PRODUCTS_PER_MIN` | `30` | Per-IP rate limit on `/search/products`. |
| `SEARCH_SUGGEST_CACHE_TTL_SECONDS` | `60` | Redis TTL for suggest cache. |
| `SEARCH_SERVICEABLE_GRID_TTL_SECONDS` | `60` | Redis TTL for the ~500 m serviceable-store grid cache. |

### Frontend `.env.local`

Lives at `frontend/.env.local`. Template is `frontend/.env.example`.

| Var | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `""` (empty) | Backend base URL. Used by `frontend/src/lib/api.ts` and `AuthContext.tsx`. Empty means relative paths — the Next.js dev server proxies `/api/v1/*` to `http://localhost:8000` via `rewrites()` in `next.config.ts`, which is what makes the ngrok mobile-test flow work without exposing the backend. In production, the web service proxies `/api/v1` to the api via `INTERNAL_API_URL` baked into the `web` image at build time (see `gcp_deployment.md`). |

Anything not prefixed with `NEXT_PUBLIC_` is server-only in Next.js 16 — clients won't see it.

---

## 2. Alembic workflow

You'll touch this often. Two rules to internalize:

1. **Every model file must be discoverable from `app.models` package import** so `target_metadata` sees its tables.
2. **Always inspect autogenerated migrations before applying** — SQLModel emits oddities for enums, JSON, arrays, and renames.

The Alembic env (`backend/app/migrations/env.py`) does:

```python
import app.models  # noqa: F401
from app.models.base import BaseSchema
target_metadata = BaseSchema.metadata
```

So if you add a new file under `backend/app/src/app/models/`, make sure `app/models/__init__.py` imports it — otherwise autogenerate won't see your tables and will silently produce an empty migration.

### Common operations

```bash
# from backend/app/

# Create a new revision from model diffs
uv run alembic revision --autogenerate -m "add seller_services table"

# Apply all pending migrations
uv run alembic upgrade head

# Roll back one step
uv run alembic downgrade -1

# Roll back to a specific revision
uv run alembic downgrade <revision-id>

# Inspect state
uv run alembic current
uv run alembic history --verbose
```

After autogenerating, **open the file under `backend/app/migrations/versions/`** and check:

- Are enum types created/dropped correctly? Postgres enums need `sa.Enum(..., name="role").create(bind)` calls in some flows.
- Are array columns (`sa.ARRAY(...)`) emitted for SQLModel `list[str]` fields? Sometimes you need to add them by hand.
- Are renames detected as drop+add? If so, switch to `op.alter_column(..., new_column_name=...)`.
- Are foreign-key cascade modes (`ondelete="CASCADE"`) preserved?

### When autogenerate produces nothing

Usually one of:

- New model file not imported in `app/models/__init__.py`.
- DB already at `head` with the same schema (no diff to detect).
- Model class missing `table=True` on the SQLModel decorator.

---

## 3. Auth & OTP (developer-facing)

We use email OTP plus JWT — no Firebase, no third-party auth provider.

### Flow

```
POST /api/v1/auth/otp/request  { email }
  → core/otp.py: hash code with HMAC(OTP_PEPPER), store in Redis under otp:code:<email>
  → email provider sends/prints the plaintext code
POST /api/v1/auth/otp/verify   { email, code, full_name? }
  → constant-time compare against stored hash
  → on first-login without name: { needs_name: true } (frontend prompts, retries)
  → on success: create_access_token(user) → { access_token, user }
```

Code references:

- `backend/app/src/app/core/otp.py` — `request_otp`, `verify_otp`, `consume_otp_key`, rate-limit exceptions
- `backend/app/src/app/core/security.py` — `create_access_token`, `decode_access_token`, role guards

### JWT contents

Issued in `core/security.py:create_access_token`:

```python
{ "sub": str(user.id), "role": user.role.value, "iat": ..., "exp": iat + ACCESS_TOKEN_TTL_MINUTES, "sid": auth_session.id }
```

`exp` is 15 minutes out (`ACCESS_TOKEN_TTL_MINUTES`), not the old 24h `JWT_EXPIRES_HOURS`. `sid` is the backing `AuthSession.id` — present whenever the access token was minted alongside a refresh session (login, seller register, referral accept); see `docs/superpowers/specs/2026-07-17-trusted-device-long-term-signin-design.md` for the full rotating-refresh-session design.

### Role-guard dependencies

Use these in route handlers — never hand-roll role checks.

```python
from app.core.security import get_current_user, get_current_seller, get_current_admin

@router.post("/me/something")
async def handler(user: User = Depends(get_current_user)): ...

@router.post("/admin-only")
async def admin_route(user: User = Depends(get_current_admin)): ...
```

`get_current_seller` accepts both Seller and Admin. `get_current_admin` is admin-only.

### Frontend storage

Token lives in `localStorage` under key `kb_token` (see `AuthContext.tsx`). Every authenticated request sends `Authorization: Bearer <token>`. The wrapper `lib/api.ts` accepts the token as the second/third arg:

```ts
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";

const { token } = useAuth();
const me = await get<User>("/api/v1/auth/me", token);
```

### Local dev tips

- `EMAIL_PROVIDER=console` prints `OTP for foo@bar: 123456` to the uvicorn stdout. Tail the backend terminal — don't hunt through Resend dashboards in dev.
- Rate limits apply in dev too. If you hit them while debugging, `redis-cli FLUSHDB` clears OTP state.
- The seller signup flow uses a separate short-lived `seller_otp` JWT (`core/security.py:create_email_verification_token`). Treat it as an email-verification token, not an access token.
- **WhatsApp (template-first):** set `WHATSAPP_PROVIDER=console` to mock sends. With WhatsApp enabled, the phone-OTP sites (seller signup, seller phone-change, delivery OTP) prefer WhatsApp and fall back to SMS only on failure — so in dev the SMS captures for those go quiet and the codes show up under `/dev-whatsapp` instead. Customer login OTP still emails, but also mirrors to WhatsApp when the customer has a verified phone. Captured messages render the template text (copy in `core/whatsapp_templates.py`); going live with Twilio only needs the `TwilioWhatsAppSender` ContentSids — no call-site changes. See the spec in `docs/superpowers/specs/2026-06-11-whatsapp-messaging-channel-design.md`.

### Gmail SMTP (temporary local-dev email delivery)

A generic SMTP provider, configured for Gmail, lets you send real notification / OTP / order emails from local dev without Resend. The `/dev-emails` mailbox still captures every message when you use the `smtp+console` variant.

**One-time Gmail setup:**

1. Enable 2-Step Verification on the Google account.
2. Create an App Password at <https://myaccount.google.com/apppasswords> (16 chars).
3. In `backend/app/.env`:

   ```bash
   EMAIL_PROVIDER="smtp+console"    # send via Gmail AND capture to /dev-emails
   SMTP_HOST="smtp.gmail.com"
   SMTP_PORT="587"
   SMTP_USERNAME="you@gmail.com"
   SMTP_PASSWORD="<16-char app password>"
   SMTP_FROM_EMAIL="you@gmail.com"  # must equal SMTP_USERNAME or a verified alias
   SMTP_USE_TLS="false"             # false = STARTTLS (587), true = implicit SSL (465)
   ```

`EMAIL_PROVIDER` values: `console` (default), `resend`, `resend+console`, `smtp` (send only), `smtp+console` (send + dev-mailbox capture). Restart the backend after changing `.env` — settings are read at startup and `get_email_sender()` is cached.

**Constraints:** the From header must match the authenticated address (Gmail rewrites it otherwise); consumer Gmail caps at ~500 recipients/day (Workspace ~2000); this is a temporary local-dev path — production still uses Resend. Dev-mailbox capture is gated to `ENVIRONMENT=development`, so `smtp+console` only records to `/dev-emails` in dev. Composite dev-mailbox rows are tagged with the real transport (`smtp` / `resend`) in the `provider` column.

### Account lifecycle (deactivate / suspend / delete)

Soft-delete only — no row is ever hard-deleted and no PII is scrubbed. `User.account_status` (`active`/`deactivated`/`suspended`/`deleted`) is the source of truth; `is_active` mirrors it. All transitions go through `services/account_lifecycle.transition()`; history is recorded in `customer_account_event`.

**Customer self-service** (`/api/v1/customers`):
- `POST /me/deactivate` — reversible; a later OTP login auto-reactivates. Blocked while open obligations exist (non-terminal order or outstanding store credit).
- `POST /me/delete/otp/request` then `POST /me/delete` (`{code, reason?}`) — terminal, confirmed by a fresh OTP in the **`account_delete`** namespace. Only an admin can restore afterwards.

**Admin supervisor** (`/api/v1/admin/customers`, admin-only, keyed by `customer_profile_id`, reason ≥10 chars):
- `GET /` (list/search `?q=&status_filter=`), `GET /{id}` (hub), `GET /{id}/activity`, and read-only `GET /{id}/{orders,addresses,notifications}`.
- `POST /{id}/{suspend,unsuspend,delete,restore}` — admins bypass the open-obligation guard (abuse response).

**Auth gates:** a `deactivated` account reactivates on OTP login; `suspended`/`deleted` are blocked at login, at `get_current_user` (kills a live access token mid-session), and at `/auth/refresh`. Account-status emails are English-only (`send_account_status_email_async`).

---

## 4. Celery / background tasks

Broker is Redis. Tasks live in `backend/app/src/app/worker.py`, with order-email dispatchers in `backend/app/src/app/services/order_emails.py`.

### Local

Run the worker in a separate terminal alongside uvicorn:

```bash
# from backend/app/
uv run celery -A app.core.celery_app worker --loglevel=info
```

### Tests

Tests run Celery in eager mode (synchronous, in-process) — no broker needed. Set in `tests/conftest.py`:

```python
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True
```

Order-email dispatchers are also patched to no-ops in every test except `test_order_emails`, because the real dispatchers spin up a worker thread that races the test event loop and pool. If you write a new task that touches the DB directly (not via the request session), patch it the same way unless you're explicitly testing it.

---

## 5. Testing patterns

We use **real Postgres** for tests, not SQLite. Database name is `khanabazaar_test` and it must exist on `localhost:5432` before pytest starts.

```bash
# create once
docker exec -it kb-postgres psql -U postgres -c "CREATE DATABASE khanabazaar_test;"
```

### Lifecycle

`tests/conftest.py` runs `drop_all` + `create_all` per function (autouse fixture), then seeds five `Language` rows (en/hi/mr/gu/pa). Catalog code assumes those exist.

### DB-session override

The session dependency is overridden once at module load:

```python
async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(test_engine) as session:
        yield session

app.dependency_overrides[get_db_session] = override_get_db_session
```

### Auth override pattern

To test a protected route as a specific role, override the role guard for the test:

```python
from app import app
from app.core.security import get_current_seller
from app.models.base import User, UserRole

async def fake_seller() -> User:
    return User(id=1, email="seller@x.com", role=UserRole.Seller, is_active=True)

app.dependency_overrides[get_current_seller] = fake_seller
try:
    res = await client.post("/api/v1/stores", json={...})
finally:
    app.dependency_overrides.pop(get_current_seller, None)
```

Always pop the override in a `finally` so it doesn't leak across tests.

### Running tests

```bash
# from backend/app/
uv run pytest -v                         # all tests
uv run pytest -v -k stores               # filter by name
uv run pytest --cov=app --cov-report=term-missing
uv run pytest tests/test_orders.py::test_create_order -v
```

---

## 6. Linting & types

### Backend

```bash
# from backend/app/
uv run ruff check .          # lint
uv run ruff format .         # autoformat
uv run mypy .                # type check
```

Ruff and mypy config live in `backend/app/pyproject.toml`. CI runs all three; expect PRs to be blocked until clean.

### Frontend

```bash
# from frontend/
npm run lint                 # ESLint 9 flat config (eslint.config.mjs)
npm run build                # also runs `next lint` + tsc
```

Type errors at build time fail the build — Next 16 doesn't ship with ts errors.

---

## 7. Frontend conventions

### Routing

App Router only. No `pages/` directory. Routes live under `frontend/src/app/<segment>/page.tsx`.

### Server vs client components

Most components are client components — they manage forms, cart, and auth. Mark with `"use client"` at the top whenever the file uses hooks, browser APIs, event handlers, or context. Server components are reserved for static layouts and `metadata` exports.

### State

Two top-level providers wrap the tree in `app/layout.tsx`:

- **`AuthContext`** (`frontend/src/lib/AuthContext.tsx`) — `dbUser`, `token`, `requestOtp`, `verifyOtp`, `logout`, plus `useRequireRole(role)` for guards.
- **`CartContext`** (`frontend/src/lib/CartContext.tsx`) — guest cart in localStorage, syncs to backend on login, exposes `addItem`, `removeItem`, `updateQty`, `clearStoreCart`.

Don't reach into localStorage directly outside these modules.

### API calls

Always go through `frontend/src/lib/api.ts`:

```ts
import { get, post, put, del, ApiError } from "@/lib/api";

try {
  const stores = await get<Store[]>("/api/v1/stores");
} catch (e) {
  if (e instanceof ApiError && e.status === 401) { /* ... */ }
}
```

`ApiError.detail` carries the FastAPI error body (string or object). Don't rebuild fetch calls inline — you'll lose the consistent error shape.

### CSS

No Tailwind. Three layers:

| Layer | Where | Purpose |
|---|---|---|
| Design tokens | `frontend/src/styles/design-tokens.css` | CSS custom properties (colors, spacing, radii). |
| Global utilities | `frontend/src/app/globals.css` | App-wide utility classes (`.btn`, `.btn-primary`, layout helpers). |
| Component styles | `<Component>.module.css` colocated next to the component | Scoped CSS Modules. |

When adding a button or card, check `globals.css` first — chances are the utility class already exists. Avoid inline styles for anything beyond one-off positioning.

### Cart storage keys

Defined in `frontend/src/lib/localCart.ts`:

- `kb_carts` — JSON map of `Cart[]` keyed by `store_id`.
- `kb_session_id` — UUID v4 for guest sessions.

On login, the merge logic in `CartContext` posts the local cart to the backend and clears localStorage. Don't read `kb_carts` directly elsewhere.

### PWA

`manifest.json` and `sw.js` live in `frontend/public/`. Registration and `<link rel="manifest">` are wired in `app/layout.tsx`. The service worker is intentionally minimal — bump its cache name when shipping new static assets you want re-fetched.

---

## 8. Async DB conventions

All routes use the async session dependency:

```python
from app.db.session import get_db_session
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

@router.get("/things")
async def list_things(session: AsyncSession = Depends(get_db_session)) -> list[Thing]:
    result = await session.exec(select(Thing).where(Thing.is_active.is_(True)))
    return result.all()

@router.post("/things")
async def create_thing(payload: ThingIn, session: AsyncSession = Depends(get_db_session)) -> Thing:
    thing = Thing(**payload.model_dump())
    session.add(thing)
    await session.commit()
    await session.refresh(thing)
    return thing
```

Rules:

- `await session.exec(...)`, `await session.commit()`, `await session.refresh(obj)`. Forgetting `await` on commit is the most common bug.
- Don't import or create sync `Session` objects — they'll deadlock against the asyncpg connection pool.
- Don't pass the session across `asyncio.create_task` boundaries. If a Celery task needs DB access, open its own engine inside the task.

---

## 9. Common gotchas

- **DSN must be `postgresql+asyncpg://`.** Cloud SQL / managed Postgres providers export a plain `postgresql://` host string and Heroku-style envs sometimes export `postgres://`; the validator rewrites both, but a hand-written `postgresql://` without rewriting still fails. Be explicit.
- **`Field(default=...)` vs `Field(default_factory=...)`.** Mutable defaults (lists, dicts, `datetime.now`) need `default_factory`. Using `default=[]` shares one list across every row.
- **Multilingual catalog rows.** When you create a `Category` or `MasterProduct`, also create translation rows for at least `en`. Records without a translation in the active locale silently disappear from listing endpoints.
- **New router not mounted.** Adding `app/api/foo.py` doesn't expose it — you must `include_router` in `app/api/__init__.py`. The list there is the authoritative route registry.
- **New model file not imported.** Adding `app/models/foo.py` doesn't make Alembic see it — add the import to `app/models/__init__.py`. Without that, `revision --autogenerate` produces an empty migration.
- **OTP rate limits in dev.** Five requests per hour per email; hit it while debugging and you're locked out for the rest of the hour. `redis-cli FLUSHDB` is the dev escape hatch.
- **Token override leakage in tests.** Always wrap `app.dependency_overrides[...] = ...` with a `try/finally` that pops it. State leaks between tests cause hours of "why does this only fail when I run the whole suite" debugging.
- **EAGER Celery + real dispatchers.** If you write a new background task that touches the DB outside the request session, patch it out in tests unless you specifically want to exercise it — see the `_patch_email_dispatch` autouse fixture for the pattern.

---

## 10. Geo / PostGIS / DIGIPIN

### Database

- Local Postgres image: `postgis/postgis:15-3.4` (`docker-compose.yml`). Drop-in compatible with `postgres:15` on disk; if you have an old volume, see `local_setup.md` for the one-time recreate.
- The `address.geo` column is a Postgres **GENERATED column** (`geography(Point, 4326) STORED`) computed from `latitude`/`longitude`. SQLModel does NOT declare it; reads happen via raw SQL. Migrations that touch the schema must NOT autogenerate-drop it — `migrations/env.py` includes a guard for this.
- `migrations/env.py` also skips PostGIS system tables (`spatial_ref_sys`) during autogen.
- Test DB: `tests/conftest.py` runs `CREATE EXTENSION IF NOT EXISTS postgis` after the schema reset, then re-applies the `geo` generated column + GiST index so tests have prod parity.

### DIGIPIN

`backend/app/src/app/utils/digipin.py` — pure-Python implementation of India Post's open 4×4-grid algorithm. Bounds: lat 2.5–38.5°, lng 63.5–99.5°. `address_from_payload` derives the code automatically when both lat/lng are present; coordinates outside India produce a null DIGIPIN but the address still saves.

### `/api/v1/geo/*` endpoints

`backend/app/src/app/api/geo.py`. All public.

| Endpoint | Purpose |
|---|---|
| `GET /geo/autocomplete?q=&session_token=` | Server-side proxy for Google Places Autocomplete. Cached 60s. |
| `GET /geo/place/{place_id}?session_token=` | Place Details (lat/lng + components). |
| `GET /geo/reverse?lat=&lng=` | Reverse geocode. Cached 24h, keyed by lat/lng rounded to 4 decimals. |
| `POST /geo/serviceability` | `{lat, lng, store_id?}` → boolean (per-store) or `{serviceable, store_count}` (global). PostGIS-backed via `ST_DWithin`. |

Server API key (`GOOGLE_MAPS_SERVER_API_KEY`) NEVER reaches the browser. The browser key (`GOOGLE_MAPS_BROWSER_API_KEY`, exposed to the frontend as `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`) is only used by the Maps JS render and must be HTTP-referrer-restricted in the GCP console.

Per-IP rate limit on `/geo/*` defaults to `30/min` (`GEO_RATE_LIMIT_PER_MIN`).

### Tests

Mock the Google client globally in any new geo test — see `tests/test_geo_endpoints.py` for the dependency-override pattern (the `Depends(_geo_rate_limit)` callable cannot be replaced via `monkeypatch.setattr`; use `app.dependency_overrides[geo_router._geo_rate_limit] = lambda: None`).

### Distance + radius

Stores are filtered/sorted by lat/lng via `GET /api/v1/stores/?lat=&lng=&sort=distance` (PostGIS `ST_DWithin` for filter, `ST_Distance` for sort). Order creation re-asserts `ST_DWithin` against the customer address — defense in depth against direct API bypass. Stores or addresses missing `geo` are treated as not-serviceable.

### Backfill

`worker.backfill_store_addresses_geocode` is a one-shot Celery task that forward-geocodes legacy `Store.address` and `SellerProfile.business_address` rows missing lat/lng. Customer addresses are NOT touched (saves Google quota; they re-fill lazily on user re-save). Idempotent. Confidence-gated (skips `partial_match=true`).

## 11. Search (Meilisearch)

Search is a separate subsystem in `app.search.*`. All search proxies through `/api/v1/search/*` — **no browser-direct Meilisearch**. See `docs/superpowers/specs/2026-05-15-search-design.md` for the full design.

### Indexes

Three Meilisearch indexes (settings + version managed by `app.search.settings`):

| Index | One doc per | Searchable fields |
|---|---|---|
| `products` | `MasterProduct` | `name_{en,hi,mr,gu,pa}`, `brand`, `category_name_en`, `subcategory_name_en`, `description_*` |
| `stores` | `Store` | `name` |
| `search_terms` | one term/locale | `term` (autocomplete corpus) |

Synonyms live in `backend/app/src/app/search/synonyms.json` (~50 Indian grocery pairs: `atta`↔`flour`, `dahi`↔`curd`, etc.). Bump `SETTINGS_VERSION` in `settings.py` to re-push settings on next app start. `_meta_vN` marker docs in each index track applied version.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/search/suggest` | Dropdown autocomplete (Recent / Suggestions / Products / Stores) |
| GET | `/api/v1/search/products` | Full results page payload + facets + sort |
| GET | `/api/v1/search/products/{id}/stores` | Per-product comparison across stores |
| GET | `/api/v1/search/stores` | Store-name search (paginated) |
| POST | `/api/v1/search/click` | Click-through analytics (no auth, best-effort) |

Rate limits: 60 req/min/IP on `/suggest`, 30 req/min/IP on `/products`. **`X-Forwarded-For` is NOT yet honored** — behind a proxy, all requests share one IP bucket (open follow-up).

### Sync pipeline

`app.search.hooks` attaches SQLAlchemy **session-level** `after_commit` + `after_rollback` listeners. On commit, accumulated dirty/new/deleted target IDs are flushed to Celery tasks in `app.search.tasks`. Each task takes a Redis lock `meili_sync:{kind}:{id}` (5 s, non-blocking) to coalesce rapid writes.

```
DB commit ──after_commit──► flush pending IDs ──.delay()──► Celery worker
                                                                │ thread-bridged asyncio.run
                                                                ▼
                                                        Meilisearch upsert
```

p95 sync lag <2 s. Rolled-back transactions drop their pending enqueues. The thread-bridged `_run_async` is in `tasks.py` — runs a fresh event loop per task so asyncpg connections don't cross-thread.

### Bulk reindex

```bash
cd backend/app
uv run python -m app.search.reindex --all                       # full rebuild
uv run python -m app.search.reindex --products                  # one index
uv run python -m app.search.reindex --products --swap-on-finish # zero-downtime alias swap
uv run python -m app.search.reindex --products --since 1h       # incremental
```

**Run after first migration + seed.** Also after bumping `SETTINGS_VERSION` or editing `synonyms.json`. Bootstrap only creates the empty indexes — it does NOT populate them.

### Celery beat jobs

Defined in `app/core/celery_app.py:26-62`.

| Task | Schedule (UTC) | Purpose |
|---|---|---|
| `search.rebuild_search_terms` | 03:15 daily | Rebuild autocomplete corpus |
| `search.prune_query_log` | 04:00 daily | Drop `search_query_log` rows older than 90 days |
| `search.verify_drift` | 04:30 daily | Sample 1000 products, diff DB vs Meili, re-enqueue divergent ones (legacy safety net; retiring once `reconcile_index` proves itself) |
| `search.reconcile_index` (`product`, shallow) | hourly at `:07` | Walk DB → Meili, drain `search:dlq:product`, re-enqueue drifted ids |
| `search.reconcile_index` (`product`, deep) | 04:30 daily | Full reconcile pass for products |
| `search.reconcile_index` (`store`, shallow) | hourly at `:22` | Same as product but for stores |
| `search.reconcile_index` (`store`, deep) | 04:45 daily | Full reconcile pass for stores |

Reconciler state lives in Redis at `search:reconcile:last:{kind}` (latest summary) and `search:reconcile:abort:{kind}` (kill switch). Dead-letter sets: `search:dlq:{product,store}` (see `app/search/dlq.py`).

Run locally: `uv run celery -A app.core.celery_app beat --loglevel=info` (in a third terminal alongside `worker`).

### Locality

`app.search.locality.get_serviceable_store_ids(session, redis, lat, lng)` runs a PostGIS `ST_DWithin` query joining `store` × `address`, caches per ~500 m grid cell in Redis for 60 s, returns `list[int] | None`. `None` means "no locality filter" — all products visible.

### Frontend

- `frontend/src/lib/searchClient.ts` — debounced (180 ms) fetch wrapper with AbortController + sequence-drop + 60 s in-memory cache. Sends `Accept-Language` header.
- `frontend/src/lib/recentSearches.ts` — localStorage helper (`kb_recent_searches`, cap 10). Cleared on logout.
- `frontend/src/components/search/SearchBar.tsx` — navbar input; desktop inline + mobile full-screen overlay. Wires ↑/↓/Enter/Esc keyboard nav with `aria-activedescendant` on the listbox children.
- Pages:
  - `/[locale]/search?q=` — global results page with filter bar.
  - `/[locale]/search/product/[productId]` — comparison page with deliverable-vs-other split + qty stepper when item already in that store/service cart.
- Store-page integration: `/[locale]/stores/[id]?q=` swaps the browse view for `<SearchResultsGrid storeId=... />`.

### Tests

- `meilisearch-test` profile in `docker-compose.yml` (port 7701). Start with `docker compose --profile test up -d meilisearch-test`.
- `meili_test_client` fixture in `tests/conftest.py` wipes + rebuilds the three indexes per test.
- Autouse `_stub_search_celery_delays` patches every `reindex_*.delay()` to a no-op so seed flushes don't fan out async work onto the wrong event loop. Tests that want to assert `.delay()` was called layer their own `patch()` inside the test body — `unittest.mock.patch` is LIFO so the inner spy wins.
- Search tests under `tests/test_search_*.py` (39 tests).

### Schema gotcha

`SearchQueryLog` declares `lat: Optional[float]` in SQLModel but the Alembic migration uses `NUMERIC(9,5)` for both lat and lng (to clamp to ~1 m precision and avoid runaway floats). If you run `alembic revision --autogenerate` you will see a spurious downgrade attempt back to `FLOAT` — discard those diffs and keep `Numeric(9,5)`. Same pattern as the geo `geo` column.

## 12. Web Push (VAPID) keys

Customer order notifications use self-hosted Web Push (VAPID + `pywebpush`). You need one keypair per environment.

Generate it once (run from `backend/app/`):

```bash
uv run python - <<'PY'
from py_vapid import Vapid01
from cryptography.hazmat.primitives import serialization
import base64
v = Vapid01(); v.generate_keys()
# Raw base64url-encoded 32-byte EC private scalar — the ONLY private-key format
# pywebpush's Vapid.from_string accepts (it does NOT parse a PKCS8 PEM string).
priv_raw = v.private_key.private_numbers().private_value.to_bytes(32, "big")
priv_b64 = base64.urlsafe_b64encode(priv_raw).rstrip(b"=").decode()
pub_raw = v.public_key.public_bytes(serialization.Encoding.X962,
    serialization.PublicFormat.UncompressedPoint)
pub_b64 = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
print("VAPID_PRIVATE_KEY=" + priv_b64)
print("VAPID_PUBLIC_KEY=" + pub_b64)
PY
```

Wire the output:

- `backend/app/.env`: `VAPID_PRIVATE_KEY` (the raw base64url private key, ~43 chars — **not** a PEM; `pywebpush.webpush()` → `Vapid.from_string` base64url-decodes it to the 32-byte scalar and a PEM fails ASN.1 parsing), `VAPID_PUBLIC_KEY`, and `VAPID_SUBJECT=mailto:you@example.com`.
- `frontend/.env.local`: `NEXT_PUBLIC_VAPID_PUBLIC_KEY` **must equal** the backend `VAPID_PUBLIC_KEY` (it is the browser's `applicationServerKey`).

**`VAPID_SUBJECT` must be a REAL, deliverable contact** — a `mailto:` with a real domain (e.g. `mailto:you@yourdomain.com`) or a real `https://` URL. Apple's push service (`web.push.apple.com`) validates it and **rejects reserved/placeholder TLDs** — `mailto:support@khanabazaar.example` (any `.example` address) returns `403 {"reason":"BadJwtToken"}` and the push silently fails. A real domain works (`.dev`, `.com`, etc.) regardless of whether mail is actually configured there. The config default is `mailto:support@khanabazaar.dev` (works); set it to a contact you actually monitor for production. (Google/FCM is lenient here, so this only bites Safari/Apple devices.)

If `VAPID_PRIVATE_KEY` is empty the push task no-ops (logs and returns) — the in-app notification bell still works, only OS push is skipped. Web Push requires a secure context (HTTPS); dev works on `localhost` and via the ngrok tunnel (`scripts/dev.sh start --tunnel`).
