# Geo-aware stores: distance sort, delivery radius, address mapping

**Date:** 2026-05-06
**Status:** Draft — awaiting user review

## Goal

Let customers sort/filter stores by real-world distance from a chosen delivery location, and prevent orders to stores whose delivery radius does not cover the customer's address. Capture courier-grade location data for every address (lat/lng + Google Place ID + India Post DIGIPIN) using a Google-Maps-driven autocomplete + map-pin UX modeled on UberEats / Swiggy.

## Decisions locked during brainstorming

| Topic | Decision |
|---|---|
| Map / geocoding provider | Google Maps Platform (proxied through backend; browser key only renders map) |
| DIGIPIN | Auto-derived server-side from lat/lng on every address write; pure-Python implementation of India Post's open algorithm |
| Distance / radius math | PostGIS `geography(Point, 4326)` + GiST index; `ST_DWithin` / `ST_Distance` |
| Delivery radius granularity | Per-store `delivery_radius_km`, default 5 km, range 0.5–50 km |
| Address verification | Soft on input (autocomplete OR pin, never blocking), serviceability filtered at use-time |
| Delivery-location source | Hybrid — guest picker on landing, logged-in users default to saved address with per-session override |
| Seller pin | Required in signup wizard for new sellers; existing stores backfilled via Google Geocoding + dashboard nudge until `pin_confirmed` |

## 1. Database schema changes

### `Address` table additions
- `latitude: float | None`, `longitude: float | None` — already present, stay nullable.
- `geo: geography(Point, 4326) | None` — **Postgres GENERATED column** (`STORED`, computed automatically from lat/lng): `geo geography GENERATED ALWAYS AS (CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography ELSE NULL END) STORED`. GiST index. No app code can drift out of sync with lat/lng.
- `digipin: str(10) | None` — derived in service layer (Python algorithm; can't be a generated column). Recomputed in `address_from_payload` whenever lat/lng change.
- `place_id: str | None` — Google Place ID when address came from autocomplete.
- `location_source: enum('manual','autocomplete','pin','geocoded')` — confidence signal. SQLModel `Enum` mapped to Postgres enum type via Alembic.

### `Store` table additions
- `delivery_radius_km: float NOT NULL DEFAULT 5.0` — seller editable, validated 0.5–50.
- `pin_confirmed: bool NOT NULL DEFAULT false` — set true when seller confirms pin.

### PostGIS setup
- Alembic migration runs `CREATE EXTENSION IF NOT EXISTS postgis;` (idempotent). Must run before the `geo` generated column is added — split into two migrations.
- **Local infra**: `docker-compose.yml` `postgres:15` image lacks PostGIS. Swap to `postgis/postgis:15-3.4` (binary-compatible drop-in). Document one-time `docker-compose down -v && docker-compose up -d` to recreate the volume.
- **Test DB**: `conftest.py` creates extension before applying migrations. CI image must also be the postgis variant.
- **Azure Postgres Flexible Server**: extension must be allowlisted via the `azure.extensions` server parameter (set to include `POSTGIS`) before `CREATE EXTENSION` succeeds. Add to Bicep in `infra/`.

### DIGIPIN module
- New file `backend/app/src/app/utils/digipin.py`.
- Pure functions: `encode(lat, lng) -> str` and `decode(code) -> tuple[float, float]`.
- Implements India Post / IIT-Hyderabad 4×4 recursive grid algorithm.
- Official bounds: lat 2.5°–38.5°, lng 63.5°–99.5°. Out-of-bounds → raises `ValueError`; caller stores null DIGIPIN, address still saves.

### Backfill data migration
- Scope: **`Store.address` and `SellerProfile.business_address` only** — operationally critical for distance math. Customer addresses are NOT backfilled (saves Google quota; they re-fill lazily next time the user opens address settings, where the autocomplete UX prompts a pin).
- One-shot Alembic data migration (or Celery task) forward-geocodes addresses with null lat/lng via Google Geocoding API.
- Confidence-gated: only writes lat/lng when `partial_match=false`. Failures stay null; seller dashboard banner persists.
- Sets `location_source='geocoded'`. `pin_confirmed` stays false (seller must still confirm).

## 2. Backend API changes

### New endpoints

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `GET` | `/api/v1/geo/autocomplete?q=&session_token=` | Server-side proxy for Google Places Autocomplete; hides API key, attaches Google session token for billing optimization | Public |
| `GET` | `/api/v1/geo/place/{place_id}?session_token=` | Proxy Google Place Details; returns lat/lng + structured components | Public |
| `GET` | `/api/v1/geo/reverse?lat=&lng=` | Reverse geocode (used after pin drop) | Public |
| `POST` | `/api/v1/geo/serviceability` | Body `{lat, lng, store_id?: int}`. With `store_id` → `{serviceable: bool}` (per-store check used at checkout). Without `store_id` → `{serviceable: bool, store_count: int}` (any-store check used by guest landing). | Public |

### Modified endpoints

`GET /api/v1/stores/`
- New optional query params: `lat`, `lng`, `radius_km`, `sort=distance`.
- When lat/lng present: filter via `WHERE store.geo IS NOT NULL AND ST_DWithin(store.geo, point, store.delivery_radius_km * 1000)` AND optional user-provided `radius_km` cap (also in meters).
- When `sort=distance`: order by `ST_Distance(store.geo, point)` ascending.
- Response: add `distance_km: float | None` to `StoreRead`. SQL converts meters → km: `ST_Distance(store.geo, point) / 1000.0 AS distance_km`.
- When no lat/lng: existing behavior (all active stores, no distance).

`POST /api/v1/orders/`
- Pre-create assertion: delivery address inside `ST_DWithin(store.geo, address.geo, store.delivery_radius_km * 1000)`.
- 422 with `{"detail": "Address outside store delivery area"}` if not. Defense in depth against direct API bypass.

Store create/edit endpoints
- Accept `delivery_radius_km` (validated 0.5–50) and `pin_confirmed`.

### Caching / cost control
- Redis cache for autocomplete keyed by `q + session_token`, 60 s TTL.
- Reverse geocode cached by lat/lng rounded to 4 decimals (~11 m bucket), 24 h TTL.
- `/geo/*` rate limited per IP at 30 req/min via existing `core/rate_limit.py` pattern.

### Config additions (`core/config.py`)
- `GOOGLE_MAPS_SERVER_API_KEY` — server-only, IP-restricted in GCP console.
- `GOOGLE_MAPS_BROWSER_API_KEY` — client key, HTTP-referrer-restricted, used only for map JS rendering.

## 3. Frontend changes

### Library
- `@vis.gl/react-google-maps` — official Google React 19 wrapper, MIT, lazy Maps JS load.
- No Tailwind. CSS Modules + design tokens.

### New components

| Component | Purpose |
|---|---|
| `<AddressAutocomplete>` | Debounced calls to `/geo/autocomplete`. On suggestion pick → `/geo/place/{id}` fills lat/lng + components + `place_id`. **Session token lifecycle**: one UUID generated when component mounts (user starts typing), reused across every autocomplete + the eventual place-details call, then **regenerated after place-details fetch returns** (Google's billing groups all calls under the same token as one "session" charged once at place-details time). |
| `<MapPicker>` | Google Map with draggable center pin + "Use my location" geolocation button. On drag-end → `/geo/reverse` re-fills city/state/pincode + lat/lng. Props: `requirePin: boolean` (default `false`; set `true` in seller signup wizard to block submission until pin placed). |
| `<DeliveryLocationContext>` | React context holding `{lat, lng, label}` where `label` is the formatted address (autocomplete `description` or reverse-geocode `formatted_address`, truncated to ~40 chars for navbar chip). Source: logged-in default address OR guest pick. Persists guest pick to `localStorage` key `kb_delivery_location`. **Cleared from localStorage on logout** by `AuthContext.logout()` (prevents leaking last guest selection to the next user on a shared device). |
| `<DeliveryLocationPicker>` | Modal triggered from navbar "Deliver to" chip. Combines autocomplete + map. Updates context. |
| `<StoreCardWithDistance>` | Existing store card + "1.2 km away" badge. Out-of-radius variant grayed with "Not delivering to your area". |

### Modified components
- `<AddressFields>` — add `<AddressAutocomplete>` above line1 input and `<MapPicker>` (toggle "Pin location for accurate delivery" by default; rendered always-open with `requirePin=true` in seller signup). lat/lng/digipin/place_id/location_source round-trip silently in `Address` type.
- `<Navbar>` — add left-side "Deliver to: [label or 'Set location']" chip opening `<DeliveryLocationPicker>`.
- Store list page (`/stores`) — read `<DeliveryLocationContext>`, append `?lat=&lng=&sort=distance` to API call. Render distance badges. Empty state "No stores deliver here yet" when zero results.
- Checkout page (`/checkout/[storeId]`) — address dropdown disables addresses outside store radius (greyed with "Outside delivery area"). One `/geo/serviceability` call per address on render, **passing `store_id`** so the backend returns a per-store boolean rather than a global count.
- Seller signup wizard — new map step (forced pin drop, defaults to geocoded address). Blocks Next until `pin_confirmed=true`.
- Seller dashboard — top banner "Confirm your store pin" until `pin_confirmed=true`. Settings: editable `delivery_radius_km` slider 0.5–50.

### Type additions (`types/index.ts`)
- `Address` gains optional `digipin`, `place_id`, `location_source`.
- `Store` gains `delivery_radius_km`, `pin_confirmed`, optional `distance_km`.

### Env
- `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY` — referrer-restricted, only powers map render.

## 4. Data flows

### Customer adds address (logged-in or guest)
1. User types into `<AddressAutocomplete>` → debounced `/geo/autocomplete` → suggestions.
2. Pick suggestion → `/geo/place/{id}` → `{lat, lng, components, place_id}`. Fields auto-fill.
3. (Optional) "Pin exact location" → `<MapPicker>` opens centered on lat/lng → drag → `/geo/reverse` re-fills.
4. Submit → backend writes `Address` → service hook computes `geo`, `digipin`, sets `location_source`.

### Guest sets delivery location
1. Navbar chip "Set location" opens `<DeliveryLocationPicker>`.
2. Same autocomplete + pin flow; no `Address` row created.
3. `{lat, lng, label}` saved to `localStorage` (`kb_delivery_location`) + context.

### Logged-in user changes delivery location per session
1. Navbar chip shows current default address label.
2. Click → picker → choose saved address OR enter ad-hoc location.
3. Ad-hoc choice persists in context + `localStorage` until next saved-address selection. No DB write.

### Store list filtering
1. `<DeliveryLocationContext>` provides lat/lng.
2. Frontend calls `GET /stores/?lat=&lng=&sort=distance`.
3. Backend `SELECT ... WHERE ST_DWithin(store.geo, point, store.delivery_radius_km*1000) ORDER BY ST_Distance(...)`.
4. Response includes `distance_km`. Empty → friendly empty state.

### Checkout serviceability gate
1. User opens `/checkout/[storeId]`.
2. Address dropdown loads saved addresses; each calls `/geo/serviceability` with `{lat, lng, store_id}` to get a per-store boolean and enable/disable the row accordingly.
3. Submit → `POST /orders/` → backend re-asserts `ST_DWithin` (defense in depth).

### Seller signup pin step
1. After address typed → wizard advances to map step.
2. Map centered on geocoded address. Pin draggable.
3. On confirm → `Address` row + `Store.pin_confirmed=true` written atomically.

### Seller backfill (one-shot data migration)
1. Scope: only `Address` rows reachable via `Store.address_id` or `SellerProfile.business_address_id` with null lat/lng. Customer addresses excluded — they re-fill lazily on next user edit.
2. For each in-scope address: forward-geocode via Google Geocoding API.
3. High confidence (`partial_match=false`) → fill lat/lng (and DIGIPIN via service helper); `geo` populates automatically (generated column). `pin_confirmed` stays `false`.
4. Low/no result → leave null. Seller sees dashboard banner until manual pin.

### DIGIPIN derivation
- Pure function called inside `address_from_payload` (and in the same path on update). Sync, sub-ms, no external call.
- Re-derived only when lat/lng change. `geo` is a Postgres generated column so it never needs explicit recomputation in app code.

## 5. Error handling, edge cases, testing

### Error handling

| Failure | Behavior |
|---|---|
| Google Places API down/quota | `/geo/autocomplete` returns 503; frontend dropdown shows "Suggestions unavailable, type address manually". Pin still works. |
| Google Maps JS load fails | `<MapPicker>` falls back to manual lat/lng inputs (advanced) + "Try again". Address still saveable without pin. |
| Browser geolocation denied | "Use my location" button shows toast "Permission denied — drag pin to your location". |
| User outside India | Reverse geocode returns non-IN country; block save with "KhanaBazaar serves India only". |
| Lat/lng outside DIGIPIN bounds | Function raises → caught → null DIGIPIN, log warning. Address still saves. |
| Pincode mismatch (typed vs reverse-geocoded) | Inline soft warning. No hard block. |
| PostGIS query on null `geo` | Filtered via `WHERE store.geo IS NOT NULL` in distance queries. |
| Backfill geocoding rate-limited | Migration sleeps + exponential backoff. Batched ≤10/sec. |
| Lat/lng edited later | `address_from_payload` re-derives DIGIPIN; `geo` regenerated automatically by Postgres (generated column). |

### Race conditions
- Inventory check + serviceability re-check happen in the same checkout transaction. Existing row-locking pattern extended with `ST_DWithin` predicate.
- Seller changes `delivery_radius_km` mid-checkout: order creation re-checks at commit; 422 → frontend reloads address picker.

### Security
- Server API key never sent to client. Browser key referrer-restricted.
- `/geo/*` rate limited per IP (30 req/min default).
- `place_id` and DIGIPIN are safe to expose.
- Reject lat/lng outside India bbox at API boundary (cheap input validation).

### Testing (`backend/app/tests/`)

New files:
- `test_digipin.py` — encode/decode round-trip on landmarks (e.g., India Gate `28.6129, 77.2295` ↔ known DIGIPIN). Boundary tests at corners of India bbox. Out-of-bounds rejection.
- `test_geo_endpoints.py` — autocomplete/place/reverse mocked at httpx layer (no real Google calls). Serviceability returns correct counts.
- `test_stores_distance.py` — seed 5 stores at known points around test point; assert order, radius filter, `distance_km` in response. Uses real PostGIS in test DB.
- `test_orders_serviceability.py` — order rejected when address outside radius; succeeds when inside.

Test infra:
- `conftest.py` adds `CREATE EXTENSION IF NOT EXISTS postgis;` to test DB setup.
- Document PostGIS requirement in `docs/development_guide.md`.
- Mock Google API client globally (similar to existing email-dispatcher no-op pattern).

Frontend: no automated tests (project policy). Manual QA checklist deferred to implementation plan.

## Out of scope (future work)

- Per-service radius (Grocery 3 km, Pharmacy 8 km) — collapse to per-store for MVP.
- Polygon delivery zones — add when sellers ask.
- Real road-distance ETA via Google Distance Matrix — display only at checkout when needed.
- Seller-approval / rejection email (separate concern).
