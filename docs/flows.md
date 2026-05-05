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
   │ hash via OTP_PEPPER ─────►  otp:code:<email>      TTL 600s
   │                              otp:cooldown:<email> TTL 60s
   │                              otp:hourly:<email>   counter, max 5/hr
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

**Tables written:** `cart`, `cartitem`. The unique key `(customer_profile_id, store_id)` on `cart` and `(cart_id, inventory_id)` on `cartitem` make the merge idempotent on retry.

After merge, every cart mutation is server-authoritative. `addItem`, `updateQty`, `removeItem`, and `clearStoreCart` go through `frontend/src/lib/remoteCart.ts` against `/carts/items*` and `/carts/{store_id}`. The provider does optimistic UI updates and rolls back on error.

## 4. Per-Store Checkout

Each store cart checks out independently — one Order per store, one payment per Order.

UI lives at `frontend/src/app/checkout/[storeId]/page.tsx`. Customer picks a `CustomerAddress` and a `PaymentMethod` (`upi` or `cash`).

**Request:** `POST /orders { store_id, customer_address_id, payment_method }`

**`place_order_for_store` pipeline** (`backend/app/src/app/services/checkout.py`):

| Step | What | Failure mode |
|------|------|--------------|
| 1 | Resolve `CustomerProfile` from JWT | 404 customer profile not found |
| 2 | Resolve + authorize address (must belong to caller) | 404/403 `invalid_address` |
| 3 | Load `Cart` + `CartItem`s for store | 404 `cart_not_found`, 400 `cart_empty` |
| 4 | `SELECT … FOR UPDATE` on every `StoreInventory` row in cart | row-locked till commit |
| 5 | Validate availability + stock per inventory | 409 `item_unavailable`, 409 `insufficient_stock` |
| 6 | Validate store still active | 409 `store_unavailable` |
| 7 | Snapshot product names (English MVP, falls back to slug) | — |
| 8 | Build `Order`, `OrderItem`s, `Payment` (status=Pending), `Delivery` (status=Pending) | — |
| 9 | Decrement `StoreInventory.stock` on locked rows | — |
| 10 | Delete `CartItem`s, then `Cart` | FK ordered |
| 11 | `session.commit()` — atomic | rollback releases inventory lock |
| 12 | `dispatch_order_placed([order_id])` → Celery | broker outage swallowed + logged |

Pricing is hardcoded at MVP: `MVP_DELIVERY_FEE = 0`, `MVP_TAX = 0`. `subtotal = sum(unit_price × qty)`, `total = subtotal + fee + tax`. Edit constants in `services/checkout.py` when fees plug in.

**Tables written:** `order`, `orderitem`, `payment`, `delivery`, `storeinventory` (stock decrement); `cartitem` + `cart` rows for that store deleted.

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

Six-step wizard at `frontend/src/app/seller/signup/page.tsx`.

```
Step 1: email
   └── POST /auth/otp/request           (same Redis-backed OTP service)
Step 2: code entry
   └── POST /auth/seller/otp/verify     → { email_token }   (10-min JWT, stored in component state)
Step 3-5: full_name, phone, business_name, services[], address, GST/FSSAI/bank
Step 6: review + submit
   └── POST /auth/seller/register { email_token, ...payload }
        ├── decode email_token → email
        ├── reject if email already registered (409)
        ├── create User(role=Seller)
        ├── create Address
        ├── create SellerProfile (verification_status=Pending)
        ├── insert SellerProfileService rows
        └── return { access_token, user }
```

After register the browser stores `kb_token` and the seller is logged in but pending. The `/seller` layout guard checks `SellerProfile.verification_status` and redirects:
- `Pending` → `/seller/signup/pending` (waiting screen)
- `Rejected` → `/seller/signup?resubmit=true` (re-edit + resubmit, which sets status back to `Pending`)
- `Approved` → seller dashboard

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
| `otp:*` (Redis) | OTP hash, cooldown, hourly counter | 60s / 600s / 1h |
| `cart`, `cartitem` (Postgres) | authenticated cart | until checkout or explicit clear |
| `order`, `orderitem`, `payment`, `delivery` (Postgres) | placed orders | permanent |
| Celery task queue (Redis broker) | order email jobs | until worker drains |
