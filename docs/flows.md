<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# User and Data Flows

End-to-end traces of every customer, seller, and admin journey through Khana Bazaar.
Each section names exact endpoints (all prefixed `/api/v1`), localStorage keys, and DB tables touched. Transient state lives in browser storage or Redis; persistent state lives in Postgres.

## 1. Guest Browsing → Local Cart

A visitor with no account can browse and build per-store carts entirely client-side. Nothing hits the backend cart endpoints until they log in.

**localStorage keys (transient, browser-only):**
- `kb_session_id` — UUID, generated once on first visit via `crypto.randomUUID()` (`frontend/src/lib/localCart.ts`)
- `kb_carts` — JSON array of `{ store_id, store_name, items[] }`; one entry per store

**Add-to-cart path (`CartContext.addItem`, `frontend/src/lib/CartContext.tsx`):**
1. User taps "Add" on a `ProductCard`.
2. `CartContext` checks `dbUser`. No user, or role !== `customer` → guest branch.
3. `localCart.addToCart(storeId, storeName, item)` mutates `kb_carts` and persists.
4. Same store + same `product_id` → quantity increments; new product → push.
5. React state updates; navbar badge re-renders via `getCartCount(carts)`.

Removing the last item from a cart deletes the cart entry from `kb_carts` so empty carts never linger.

## 2. OTP Sign-In

```
[email entry]
   │  POST /auth/otp/request { email }
   ▼
[FastAPI]                         [Redis]
   │ generate 6-digit code
   │ hash via OTP_PEPPER ─────►  otp:email:code:<email>      TTL 600s
   │                              otp:email:cooldown:<email> TTL 60s
   │                              otp:email:hourly:<email>   counter, max 5/hr
   │ (phone-OTP uses the same primitives under the namespace `otp:phone:*`.)
   │ enqueue email to Resend or log to console
   ▼
[email arrives]
   │  POST /auth/otp/verify { email, code, full_name? }
   ▼
[FastAPI]
   │ HMAC-compare hash; track attempts (max 5)
   │ if new email + no full_name → 200 { needs_name: true }
   │ else upsert User + CustomerProfile
   │ delete all otp:* keys (consume_otp_key)
   │ create_access_token: HS256, sub=user.id, role=user.role, exp=24h
   ▼
[browser]
   │ localStorage.setItem("kb_token", access_token)
   │ AuthContext sets dbUser + token in memory
```

**Endpoints** (`backend/app/src/app/api/auth.py`):
- `POST /auth/otp/request` — 200 `{ ok, expires_in }`; 429 `rate_limited` with `retry_after`
- `POST /auth/otp/verify` — 200 `{ access_token, token_type, user, needs_name }`; 400 `invalid_code`, 410 `code_expired_or_used`, 429 `too_many_attempts`
- `GET /auth/me` — bearer-token round-trip on app boot to rehydrate `dbUser`

**Tables written on first sign-in:** `user`, `customerprofile`. Token (transient on server, since stateless) is persisted only in `kb_token`. Logout clears `kb_token` and resets `AuthContext` state.

## 3. Cart Merge on Login

When a guest signs in, their `kb_carts` get pushed to the backend exactly once.

`CartContext` watches `[authLoading, dbUser, token]` and tracks `lastSyncedUserId` in a ref to avoid double-syncing on rerender:

1. Auth resolves, `dbUser.role === "customer"`, `lastSyncedUserId !== dbUser.id`.
2. Read `localCart.getAllCarts()`. Empty? Fall through to plain `listCarts`.
3. Build payload: `[{ store_id, items: [{ inventory_id, quantity }] }]`. Items missing an `inventory_id` (legacy guest entries) are filtered out.
4. `POST /carts/sync` with bearer token.
5. Server iterates each store: validates store active, validates each `StoreInventory` belongs to that store and `is_available`. Drops invalid items into `dropped[]` with reason (`store_unavailable | unknown_inventory | item_unavailable`). Survivors get inserted into the customer's `Cart` / `CartItem` rows; same-inventory hits accumulate quantity.
6. Response returns canonical server cart state. Client calls `localCart.clearAllCarts()` and stamps `lastSyncedUserId.current = dbUser.id`.

**Tables written:** `cart`, `cartitem`. The unique key `(customer_profile_id, store_id, service_id)` on `cart` and `(cart_id, inventory_id)` on `cartitem` make the merge idempotent on retry. Sync auto-derives `service_id` per item from the inventory's product chain so legacy single-key payloads keep working.

After merge, every cart mutation is server-authoritative. `addItem`, `updateQty`, `removeItem`, and `clearStoreServiceCart` go through `frontend/src/lib/remoteCart.ts` against `/carts/items*` and `/carts/{store_id}/{service_id}`. The provider does optimistic UI updates and rolls back on error.

## 4. Per-Store-Per-Service Checkout

Carts are keyed `(customer_profile_id, store_id, service_id)` — a single store can host one sub-basket per service (Grocery, Food, Pharmacy, …), and each sub-basket checks out as its own `Order` with its own `Payment` + `Delivery`. Sibling sub-baskets at the same store stay intact when one of them is placed.

**Cross-service add auto-splits, no modal.** When a customer adds a product whose service differs from any existing cart at that store, `CartContext` silently routes the item into a new `(store, service)` sub-basket. The previous "one cart per store" merge prompt is gone. Each add-to-cart call validates two invariants:

- **Seller-offers-service**: the store's seller must currently offer the target service. Failure → `409 service_unavailable`.
- **Inventory ↔ service match**: the inventory's `MasterProduct → Subcategory → Category → Service` chain must resolve to the same `service_id` the customer is adding under. Failure → `400 service_mismatch` (catches catalog drift or a forged `service_id`).

UI lives at `frontend/src/app/checkout/[storeId]/page.tsx`, scoped to one `service_id`. Customer picks a `CustomerAddress` and a `PaymentMethod` (`upi` or `cash`).

**Request:** `POST /orders { store_id, service_id, customer_address_id, payment_method }`

**`place_order_for_store_service` pipeline** (`backend/app/src/app/services/checkout.py`):

| Step | What | Failure mode |
|------|------|--------------|
| 1 | Resolve `CustomerProfile` from JWT | 404 customer profile not found |
| 2 | Resolve + authorize address (must belong to caller) | 404/403 `invalid_address` |
| 3 | Load `Cart` + `CartItem`s for `(store_id, service_id)` | 404 `cart_not_found`, 400 `cart_empty` |
| 4 | **PostGIS serviceability assertion**: `ST_DWithin(store.geo, address.geo, store.delivery_radius_km*1000)` | **422 `Address outside store delivery area`** |
| 5 | `_validate_service_active_for_store(store_id, service_id)` — seller still offers this service | **409 `service_unavailable`** |
| 6 | `SELECT … FOR UPDATE` on every `StoreInventory` row in cart | row-locked till commit |
| 7 | `_assert_locked_inventory_matches_service(...)` — re-derive `service_id` from each locked product chain and compare to payload | **409 `service_mismatch`** |
| 8 | Validate availability + stock per inventory | 409 `item_unavailable`, 409 `insufficient_stock` |
| 9 | Validate store still active | 409 `store_unavailable` |
| 10 | Snapshot product names AND `service_name_snapshot` (English MVP, slug fallback) | — |
| 11 | Build `Order` (carries `service_id` + `service_name_snapshot`), `OrderItem`s, `Payment` (status=Pending), `Delivery` (status=Pending) | — |
| 12 | Decrement `StoreInventory.stock` on locked rows | — |
| 13 | Delete `CartItem`s, then this sub-basket's `Cart` row (sibling carts untouched) | FK ordered |
| 14 | `session.commit()` — atomic | rollback releases inventory lock |
| 15 | `dispatch_order_placed([order_id])` → Celery | broker outage swallowed + logged |

Steps 5 and 7 are deliberate **defense-in-depth against catalog drift**: between cart-load and checkout the seller may have revoked the service (→ 409 `service_unavailable`) or admin may have re-parented a subcategory to a different service (→ 409 `service_mismatch`). Both raise cleanly so a half-placed cross-service order is impossible. No automatic cart purge happens — the customer is informed and can prune the sub-basket themselves.

The serviceability assertion (step 4) is **defense in depth** against direct API bypass — the frontend `<AddressPicker>` already disables out-of-radius rows by calling `POST /api/v1/geo/serviceability` per saved address, but the backend re-checks at order time so a customer cannot POST around the picker. Stores or addresses missing `geo` (null lat/lng) are treated as not-serviceable so couriers never end up with un-pinpointed deliveries.

Pricing is hardcoded at MVP: `MVP_DELIVERY_FEE = 0`, `MVP_TAX = 0`. `subtotal = sum(unit_price × qty)`, `total = subtotal + fee + tax`. Edit constants in `services/checkout.py` when fees plug in.

**Order email subject + body include the service name** (snapshot at placement time — `Order.service_name_snapshot`, English with slug fallback), so customers and sellers can tell apart two simultaneous orders from the same store. See `services/order_emails.py`.

**Tables written:** `order` (with `service_id` + `service_name_snapshot`), `orderitem`, `payment`, `delivery`, `storeinventory` (stock decrement); `cartitem` + the matching `(store_id, service_id)` `cart` row deleted (sibling sub-baskets at the same store are untouched).

## 5. Order Fulfillment

`OrderStatus` enum (`backend/app/src/app/models/commerce.py`): `pending`, `paid`, `packed`, `dispatched`, `delivered`, `cancelled`.
The `paid` value is reserved; today the lifecycle skips it and marks `Payment.status = paid` only when delivery completes.

**Legal transitions** (`backend/app/src/app/services/orders.py:LEGAL_TRANSITIONS`):

```
pending ──► packed ──► dispatched ──► delivered   (terminal)
   │           │            │
   └───────────┴────────────┴──► cancelled        (terminal)
```

- Forward transitions via `POST /orders/{id}/transition { to: "packed" | "dispatched" | "delivered" }`. Authorized for the seller who owns the store, or any admin.
- `delivered` writes `Delivery.delivered_at` and flips `Payment.status` to `paid` + sets `paid_at`.
- Cancellation via `POST /orders/{id}/cancel`. Customer can cancel only while `pending`; seller/admin can cancel any non-terminal order. Cancel re-locks every line's `StoreInventory` row and `restock`s the quantities.

**Email side-effects** (`backend/app/src/app/services/order_emails.py`, dispatched as Celery tasks):

| Event | Customer | Seller |
|-------|----------|--------|
| Order placed | one summary email per checkout (all orders) | one per order at their store |
| Status transition (packed/dispatched/delivered) | always | not by default |
| Cancellation | yes | yes (`notify_seller=True`) |

Broker errors (Kombu/Redis outage) get caught and logged in `_safe_delay`; the request path never fails because of email infra.

## 6. Seller Signup → Approval

Eight-step wizard at `frontend/src/app/(operator)/seller/signup/page.tsx`. Two OTP gates (email and phone) precede the data-entry steps.

```
Step 1: email
   └── POST /auth/otp/request           (Redis-backed OTP, namespace=email)
Step 2: email-code entry
   └── POST /auth/seller/otp/verify     → { email_token }   (10-min JWT, type=seller_email)
Step 3: phone (E.164 +91)
   └── POST /auth/seller/phone/otp/request { email_token, phone }
        ├── decode email_token (proves email is verified)
        ├── normalize_phone → +91XXXXXXXXXX
        ├── reject if SellerProfile.phone exists (409 phone_already_registered, no SMS sent)
        └── store hashed code in Redis (namespace=phone), dispatch SMS
Step 4: phone-code entry
   └── POST /auth/seller/phone/otp/verify { email_token, phone, code }
        └── on success: → { signup_token }   (10-min JWT, type=seller_signup, sub=email, phone=+91…)
Step 5-7: full_name, business_name, services[], address, GST/FSSAI/bank
Step 8: review + submit
   └── POST /auth/seller/register { signup_token, ...payload }   (no email, no phone — both from token claims)
        ├── decode signup_token → (email, phone)
        ├── reject if email already registered (409 email_already_registered)
        ├── reject if phone already registered (409 phone_already_registered)  (race-window defence in depth)
        ├── create User(role=Seller)
        ├── create Address
        ├── create SellerProfile (verification_status=Pending)
        ├── insert SellerProfileService rows
        └── return { access_token, user }
```

After register the browser stores `kb_token` and the seller is logged in but pending. The `/seller` layout guard checks `SellerProfile.verification_status` and redirects:
- `Pending` → `/seller/signup/pending` (waiting screen)
- `Rejected` → `/seller/signup?resubmit=true` (re-edit + resubmit, jumps to step 5; re-OTP not required because resubmit uses an authenticated PATCH path, not `/auth/seller/register`)
- `Approved` → seller dashboard

**SMS provider**: `SMS_PROVIDER=console` (dev/test, logs `[SMS] to=+91… code=…` to stdout) or `twilio` (production, raw httpx POST to Twilio Messages API; no SDK). Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` for production.

**Admin queue** (`backend/app/src/app/api/sellers.py`):
- `GET /sellers/admin/applications?status=pending|approved|rejected|all` — list w/ joined Address, services
- `GET /sellers/admin/applications/counts` — sidebar badges
- `PATCH /sellers/admin/{seller_id}/verify { action: "approve" | "reject", rejection_reason? }`
  - On approve: requires ≥1 service, flips status to `Approved`, idempotently provisions a `Store` row with the business address copied (subsequent address edits do not propagate; sellers update store address via store-settings).
  - On reject: requires non-empty `rejection_reason`, flips to `Rejected`. IntegrityError on a race re-fetches and returns the winning state.

**Tables written:** `user`, `address`, `sellerprofile`, `sellerprofileservice`, `store` (on approval).

## 7. Admin Catalog Management

Admin builds the master catalog that all sellers select from. Multilingual via translation tables; default language `en`. Supported codes (enum `Language` in `models/catalog.py`): `en`, `hi`, `mr`, `gu`, `pa`.

```
service ──< category ──< subcategory ──< masterproduct
   │            │             │                │
   ▼            ▼             ▼                ▼
servicetranslation
            categorytranslation
                         subcategorytranslation
                                          masterproducttranslation
```

Each translation table carries `(parent_id, language_code, name, …)` with a unique constraint on the pair. `MasterProductTranslation` powers the cart and order-item snapshots — checkout joins it to capture `product_name_snapshot`, falling back to `MasterProduct.slug` when no translation exists.

Admin endpoints live in `backend/app/src/app/api/catalog.py` and `meta.py` and require the admin role guard `get_current_admin`.

## 8. Inventory & Per-Store Availability

After approval, the seller manages a `StoreInventory` row per master product they carry.

| Field | Notes |
|-------|-------|
| `store_id` | seller's store |
| `product_id` | FK to `masterproduct` |
| `price` | per-store price (rupees) |
| `stock` | integer, decremented on order placement, restocked on cancel |
| `is_available` | hard kill switch independent of stock |

Customer-facing reads:
- Store catalog page (`frontend/src/app/stores/[id]/`) lists `StoreInventory` joined to `MasterProduct` + translation, filtered to `is_active` stores and `is_available` rows.
- `CartItemAdd` and `CartSync` both check `inv.store_id == payload.store_id` to prevent cross-store smuggling, and `inv.is_available` to lock out disabled items.
- Checkout re-validates availability + stock under a row lock — a seller flipping `is_available` between cart load and submit cleanly produces 409, not a half-placed order.

## 9. Quick Reference: Where State Lives

| Layer | Example | Lifetime |
|-------|---------|----------|
| `kb_session_id` (localStorage) | guest UUID | until browser data cleared |
| `kb_carts` (localStorage) | guest cart map | until login (cleared post-sync) or browser data cleared |
| `kb_token` (localStorage) | JWT | 24h or until logout |
| `kb_delivery_location` (localStorage) | guest + ad-hoc {lat,lng,label} | until logout or explicit clear |
| `otp:*` (Redis) | OTP hash, cooldown, hourly counter | 60s / 600s / 1h |
| `geo:auto:*` (Redis) | autocomplete cache by session_token | 60s |
| `geo:rev:*` (Redis) | reverse-geocode cache by rounded lat/lng | 24h |
| `rl:geo:*` (Redis) | per-IP rate-limit bucket for /geo/* | 60s |
| `kb_recent_searches` (localStorage) | last 10 user search terms | until logout or explicit clear |
| `suggest:*` (Redis) | search suggest response by sha1(q\|grid\|store\|locale) | 60s |
| `serviceable:*` (Redis) | serviceable store IDs per ~500m grid cell | 60s |
| `ratelim:search:*` (Redis) | per-IP rate-limit bucket for /search/* | 60s |
| `meili_sync:product:*` / `meili_sync:store:*` (Redis) | sync coalesce lock | 5s |
| `search_query_log` (Postgres) | search analytics rows | 90 days (Celery beat prune) |
| Meilisearch `products` / `stores` / `search_terms` indexes | searchable docs | rebuilt from Postgres via reindex CLI or after_commit sync |
| `cart`, `cartitem` (Postgres) | authenticated cart | until checkout or explicit clear |
| `order`, `orderitem`, `payment`, `delivery` (Postgres) | placed orders | permanent |
| `address.geo` (Postgres GENERATED column) | `geography(Point, 4326)` derived from lat/lng | auto-recomputed on insert/update |
| `address.digipin` (Postgres) | India Post 10-char grid code | recomputed by `address_from_payload` on lat/lng change |
| Celery task queue (Redis broker) | order email jobs, geo backfill | until worker drains |


## 9. Seller bulk inventory edit

1. Seller opens `/seller/inventory/bulk` from the toolbar link on `/seller/inventory`.
2. Frontend loads three resources in parallel:
   - `GET /api/v1/stores/my` → seller's store
   - `GET /api/v1/sellers/me/eligible-products` → products in seller's approved services (each row carries an `in_inventory` flag for the seller's store)
   - `GET /api/v1/stores/{id}/inventory/all` → existing rows
3. Existing inventory rows render in an editable spreadsheet. The picker side panel offers add-from-eligible (drill-down by service → category → subcategory + free-text search; already-stocked products are hidden).
4. Seller edits prices/stocks (optionally using the bulk-fill toolbar to set price/stock or apply ±N% to selected rows) and clicks **Save N change(s)**.
5. Frontend pre-validates each row. Save is disabled while any row has errors OR when no row is dirty.
6. `PUT /api/v1/stores/{id}/inventory/bulk` body: `{ "items": [{ product_id, price, stock, is_available }] }`.
7. Server: authorize store ownership → enforce 200-row cap → field validation (price/stock ranges, no duplicate product_id) → service-membership check via `assert_products_in_seller_services` → upsert in a single transaction. Existing rows are locked in deterministic id order via `lock_inventory_rows()` to avoid checkout deadlocks (same pattern as `services/checkout.py`).
8. On any failure: HTTP 4xx with structured per-row errors; the transaction rolls back; nothing persists.
9. On success: returns the upserted `StoreInventory` rows. Frontend clears dirty/error state and rebases the sheet to the saved values.

The single-row `POST /api/v1/stores/{id}/inventory` endpoint shares the same service-membership validator, so a seller who is approved only for Grocery cannot stock a Pharmacy product through either path. Pre-existing inventory rows that violate the new constraint are grandfathered (not deleted); operators can run `python -m app.db.scripts.audit_inventory_service_membership` to log them.

## 10. Geo: Delivery location, address pin, distance browse

Three intertwined flows. State lives in:

- `localStorage["kb_delivery_location"]` — guest + ad-hoc delivery location (cleared on logout, cross-tab synchronized via `storage` event)
- `Address.{latitude, longitude, geo, digipin, place_id, location_source}` — per address row
- `Store.{delivery_radius_km, pin_confirmed}` — per store

### 10.1 Customer adds / edits address

```
Browser                                    Backend
   |                                          |
   | type into <AddressAutocomplete>          |
   | GET /api/v1/geo/autocomplete?q=&token=   |--- Redis cache lookup (60s)
   |                                          |--- proxy → Google Places Autocomplete
   |<------- predictions -------------------- |    (server key, not exposed)
   |                                          |
   | pick suggestion                          |
   | GET /api/v1/geo/place/{id}?token=        |--- proxy → Google Place Details
   |<------- {lat, lng, components, place_id} |
   |  (autocomplete session token regenerated |
   |   so Google bills as one session)        |
   |                                          |
   | (optional) drag <MapPicker> pin          |
   | GET /api/v1/geo/reverse?lat=&lng=        |--- Redis cache lookup (24h, lat/lng rounded to 4dp)
   |                                          |--- proxy → Google Geocoding (reverse)
   |<------- {formatted_address, components}--|
   |                                          |
   | POST /customers/me/addresses             |--- address_from_payload(body.address)
   |                                          |    derives DIGIPIN from lat/lng
   |                                          |    Postgres generates `geo` column
   |<------- 200 ---------------------------- |
```

`location_source` field tracks how lat/lng were acquired (`autocomplete`, `pin`, `geocoded`, `manual`). Used downstream by seller-approval logic to decide whether to inherit `pin_confirmed=true` on the auto-created Store.

### 10.2 Guest sets delivery location

Same UI as 10.1 but no DB write. `<DeliveryLocationPicker>` (modal) opens from the navbar "Deliver to" chip, lets the guest autocomplete or pin a location. On confirm: `{lat, lng, label}` saved to `localStorage["kb_delivery_location"]`. The store-list page reads it via `useDeliveryLocation()` and re-fetches.

### 10.3 Distance-sorted store list

```
Browser                                    Backend
   |                                          |
   | <DeliveryLocationContext> has {lat, lng} |
   | GET /stores/?lat=&lng=&sort=distance     |
   |                                          |--- WHERE store.geo IS NOT NULL
   |                                          |    AND ST_DWithin(store.geo, point,
   |                                          |        store.delivery_radius_km * 1000)
   |                                          |--- ORDER BY ST_Distance ASC
   |<-- [{...store, distance_km}, ...] ------ |
```

Stores without a `geo` (null lat/lng) are excluded — they cannot be courier-located. When zero results, frontend shows "No stores deliver here yet". Optional `&radius_km=` query param shrinks the per-store radius further (cap = `LEAST(store.delivery_radius_km, user_cap)`).

### 10.4 Checkout serviceability gate

```
<AddressPicker> (per saved address)        Backend
   POST /geo/serviceability {lat, lng, store_id}
                                          |--- ST_DWithin(store.geo, point, radius)
                                          |
   <select><option disabled> ←-- {serviceable: false}
```

The address dropdown disables un-serviceable rows in the UI. On submit, `POST /orders` re-asserts the same `ST_DWithin` (defense in depth, see §4 step 4).

### 10.5 Seller signup pin step

Wizard step 6 now requires a map pin in addition to the typed address. `<AddressFields requirePin>` renders the `<MapPicker>` always-open; user drags the pin (or hits "Use my location"); reverse-geocode fills city/state/pincode + sets `location_source='pin'`. The Next button checks `address.latitude == null` and blocks until both are set.

### 10.6 Seller pin confirmation + radius adjust

After approval, the seller dashboard:

- Shows a "Confirm your store pin" banner until `Store.pin_confirmed=true`. New sellers who pinned during signup inherit `pin_confirmed=true` automatically (admin approval logic).
- Renders a slider (0.5 km – 50 km) bound to `Store.delivery_radius_km`. Drag-end PATCHes `/api/v1/stores/{id}` `{ delivery_radius_km }`.

### 10.7 Backfill (one-shot)

Legacy stores created before the geo work have `Store.address.latitude IS NULL`. Run the Celery task:

```
celery -A app.core.celery_app call geo.backfill_store_addresses
```

Forward-geocodes via Google for `Address` rows reachable through `Store.address_id` or `SellerProfile.business_address_id`, gated by `partial_match=false`. Customer addresses are NOT touched (they re-fill lazily on next user-driven save). Idempotent.

## 11. Search (Meilisearch)

### 11.1 Customer types in the navbar search bar

```
[User typing "naan"]
   │  (debounce 180ms, AbortController cancels prior request)
   ▼
[SearchBar (frontend)]
   ▼
GET /api/v1/search/suggest?q=naan&lat=&lng=
   │  Accept-Language: en|hi|mr|gu|pa
   ▼
[FastAPI search router]
   ├── Redis GET suggest:<sha1(q|grid|store|locale)>   ─ cache HIT → return
   ├── locality.get_serviceable_store_ids(lat,lng)     ─ PostGIS + 60s Redis grid
   ├── Meilisearch search_terms.search(q, filter=locale)
   ├── Meilisearch products.search(q, filter="store_ids IN [...]")
   ├── Meilisearch stores.search(q, filter="is_active")
   ├── Best-effort INSERT search_query_log
   └── 200 OK { query_id, terms[], products[], stores[] }     X-Search-Query-ID header
       │  cached in Redis 60s
       ▼
[Dropdown sections: Recent / Suggestions / Products / Stores / See-all]
```

### 11.2 Customer clicks a product result

```
[Click on product row]
   ├── searchClient.logClick({ query_id, clicked_product_id, position })
   │      POST /api/v1/search/click  → 204
   │         └── UPDATE search_query_log SET clicked_product_id=… WHERE query_id=…
   └── router.push("/{locale}/search/product/{productId}")
        ▼
GET /api/v1/search/products/{id}/stores?lat=&lng=
   ├── Postgres join StoreInventory × Store × Address
   ├── Annotate per-offer is_serviceable + distance_km via locality cache
   └── Sort offers by price ascending
       ▼
[Render: deliverable stores first; <details> "Other stores (N)" collapsed]
   ├── If item already in cart for (store, service) → render ± qty stepper
   └── Else → render Add button
```

### 11.3 Customer searches inside a store page

```
[/stores/{id}?q=atta]
   ▼
Store page detects ?q=, swaps browse view for <SearchResultsGrid storeId={id} q=...>
   ▼
GET /api/v1/search/products?q=atta&store_id={id}
   ├── locality skipped (store_id scope wins)
   └── filter="store_ids = {id} AND is_active = true"
   ▼
Annotate per_store_offers with is_serviceable + distance, derive min_price_bucket facet
   ▼
Grid renders; "← Back to browse" link clears ?q=.
```

### 11.4 Sync from DB write to searchable

```
Seller / admin / customer write to the DB
   │
   ▼
[SQLAlchemy session commit]
   ├── search.hooks.after_flush  collects dirty IDs per kind
   ├── search.hooks.after_commit fans out Celery .delay() calls
   └── after_rollback drops the pending IDs
        ▼
[Celery worker process]
   ├── Take Redis lock meili_sync:{kind}:{id} (5s, non-blocking)
   │     └── concurrent worker for same id returns immediately (coalesce)
   ├── Build doc via app.search.serialize.build_product_document
   └── Upsert into Meilisearch
        ▼ (~50–200 ms async)
Searchable. p95 sync lag <2 s.
```

### 11.5 Periodic Celery beat (UTC)

| Time | Task | What it does |
|---|---|---|
| 03:15 | `search.rebuild_search_terms` | Wipe + rebuild autocomplete corpus from current translations |
| 04:00 | `search.prune_query_log` | `DELETE FROM search_query_log WHERE created_at < NOW() - INTERVAL '90 days'` |
| 04:30 | `search.verify_drift` | Sample 1000 products, diff DB-built doc vs Meilisearch doc on a tight key subset, re-enqueue divergent ones |

### 11.6 First-deploy bootstrap (one-shot)

```
$ uv run python -m app.search.reindex --all
{'products': 1500, 'stores': 90, 'search_terms': 1900}
```

Required after the first migration + seed and after dropping the `meili_data` Docker volume. Meilisearch starts empty; bootstrap on app startup only ensures the indexes + settings exist — it does not populate documents.
