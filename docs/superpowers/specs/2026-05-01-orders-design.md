<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Orders — Design

**Date:** 2026-05-01
**Status:** Draft
**Scope:** Implement end-to-end order placement and fulfillment for KhanaBazaar. Customers can checkout from their multi-store cart, sellers receive and progress orders, and each role's dashboard surfaces active orders. Cash-on-Delivery is the only payment method for this iteration.

## Motivation

The platform has product browsing, store/inventory management, customer profiles with saved addresses, and a fully working multi-store cart that lives in `localStorage`. The cart's "Proceed to Checkout" button has been disabled with a "coming in a future phase" tooltip since cart launch.

Order, OrderItem, Payment, and Delivery models already exist in `backend/app/src/app/models/commerce.py` from earlier schema work, but no API or UI exposes them. Without an order flow there is no path from cart to revenue, and sellers have no inbox to act on. This feature closes that loop:

- Customers can place orders from their cart and see what they bought.
- Sellers receive orders in their dashboard and progress them through pack/dispatch/deliver.
- Admins get platform-wide visibility and a cancel-override for support cases.
- All three roles see "active orders" prominently on their dashboard landings.

Payment gateway integration is intentionally deferred. COD is sufficient for the hyperlocal Indian market launch and exercises the full lifecycle without external dependencies.

## Scope

In scope:

- Cash-on-Delivery payment only. `Payment` row created at order time with `status=Pending, method=Cash`; flips to `Paid` when the order is marked `Delivered`.
- Customer cart persistence in the database for logged-in users. Every add/remove/qty edit hits the backend so the cart follows the user across devices.
- Cart sync from `localStorage` to DB on login (quantities sum on conflict).
- Single "Place Order" action on the cart page that fans out into one `Order` per store atomically in one transaction.
- Stock decrement (`StoreInventory.stock`) on order creation and automatic restock on cancellation.
- `Order.delivery_address_id` stores the underlying `Address.id`. Checkout takes the customer-facing `customer_address_id` (i.e. a `CustomerAddress` row owned by the user) and resolves it server-side.
- Seller-driven status lifecycle: `Pending → Packed → Dispatched → Delivered`. `Cancelled` reachable from any non-terminal state per role rules.
- Customer can cancel only while `Pending`. Seller can cancel anytime before `Delivered`. Admin can cancel any non-terminal order.
- Order list and detail pages for all three roles (customer, seller, admin).
- "Active Orders" widget added to each role's existing dashboard landing.
- Email notifications via Celery + Resend: seller alerted on new order, customer gets order confirmation, both notified on status changes.
- 15-second polling for dashboard freshness (no SSE/WebSockets in this iteration).
- Backend pytest coverage for cart, checkout, transitions, cancellation, RBAC, and stock races.

Out of scope:

- Real payment gateway integration (UPI/Razorpay). The `PaymentMethod` enum is left as `Upi | Cash`; future work adds gateway hooks.
- Live updates via Server-Sent Events or WebSockets. Polling is sufficient at MVP scale.
- Driver/delivery-partner role. Sellers manage delivery state themselves.
- Order history pagination UI (capped at last 50).
- Customer ability to edit an order after placement.
- Refund flows beyond marking `Payment.status = Refunded` on cancel of a Paid order.
- Frontend test framework. None exists in `frontend/` today and adding one is its own project.
- Reviews, ratings, or favorites tied to delivered orders (separate feature).

## Recommended Approach

Single-transaction fan-out checkout with a thin API layer over a service module that owns all business rules.

The cart endpoint exists primarily to keep multi-device cart state in sync; the order endpoint reads from the DB cart at checkout time so the request payload is just `{address_id}`. All state transitions (place, transition, cancel) route through service functions in `backend/app/src/app/services/` so RBAC checks, side effects (Payment update, restock, email dispatch), and validity rules live in one place. API handlers stay thin: auth dependency, request parse, service call, response serialize.

On the frontend, the existing `CartContext` is split so guests use a `localCart` adapter and logged-in users use a `remoteCart` adapter that mirrors every operation to the backend. Optimistic UI hides the network round-trip on add/remove. Three role-specific order routes (`/account/orders`, `/seller/orders`, `/admin/orders`) share a small set of components (`OrderCard`, `OrderTimeline`, `OrderStatusBadge`, `OrderActionButtons`) that vary their behavior by `role` prop.

Rejected alternatives:

- **Per-store checkout buttons.** Would let customers checkout one store at a time but multiplies user actions and breaks the "one tap" expectation.
- **Mock UPI flow.** Adds throwaway UI before a real gateway is integrated. COD is a real payment method that exercises the full schema without pretending.
- **Server-Sent Events for dashboard updates.** Higher infra and complexity for a problem polling solves at current scale.
- **Skipping the DB cart.** Caller wanted multi-device cart continuity; localStorage-only does not deliver that.

## Architecture

### New backend modules

```
backend/app/src/app/
├── api/
│   ├── carts.py              # NEW — cart CRUD + sync
│   └── orders.py             # NEW — list/detail/place/transition/cancel
├── services/                 # NEW directory
│   ├── __init__.py
│   ├── checkout.py           # place_orders_from_cart()
│   ├── inventory.py          # decrement_stock(), restock()
│   └── orders.py             # transition_order_status(), cancel_order()
├── core/security.py          # MODIFIED — add get_current_customer dependency
└── worker.py                 # MODIFIED — 3 new Celery tasks
```

`api/__init__.py` mounts the two new routers under `/api/v1/carts` and `/api/v1/orders`.

### New frontend modules

```
frontend/src/
├── app/
│   ├── account/
│   │   ├── page.tsx                    # MODIFIED — add ActiveOrdersWidget
│   │   └── orders/
│   │       ├── page.tsx                # NEW — customer order list
│   │       └── [id]/page.tsx           # NEW — customer order detail
│   ├── seller/
│   │   ├── page.tsx                    # MODIFIED — add ActiveOrdersWidget
│   │   └── orders/
│   │       ├── page.tsx                # NEW — seller order list
│   │       └── [id]/page.tsx           # NEW — seller order detail with action buttons
│   ├── admin/
│   │   ├── page.tsx                    # NEW or MODIFIED — add ActiveOrdersWidget
│   │   └── orders/
│   │       ├── page.tsx                # NEW — admin all-orders view
│   │       └── [id]/page.tsx           # NEW — admin detail with cancel override
│   └── cart/page.tsx                   # MODIFIED — wire up checkout + AddressPicker
├── components/orders/                  # NEW directory
│   ├── ActiveOrdersWidget.tsx
│   ├── OrderCard.tsx
│   ├── OrderTimeline.tsx
│   ├── OrderStatusBadge.tsx
│   ├── OrderItemList.tsx
│   ├── OrderActionButtons.tsx
│   └── AddressPicker.tsx
├── lib/
│   ├── cart.ts                         # MODIFIED — shrink to shared types/helpers
│   ├── localCart.ts                    # NEW — extracted guest logic
│   ├── remoteCart.ts                   # NEW — API client for cart endpoints
│   ├── CartContext.tsx                 # MODIFIED — backend selection by useAuth, sync on login
│   └── orders.ts                       # NEW — API client for order endpoints
└── types/index.ts                      # MODIFIED — add Order, OrderItem, OrderStatus, PaymentStatus, DeliveryStatus; extend CartItem with inventory_id
```

### Module boundaries

- `services/checkout.py` knows how to read carts, validate, fan out, and clear. It calls `services/inventory.py` for stock changes.
- `services/orders.py` owns the state machine: legal transitions, role-based authorization, side effects (Payment update on Delivered, restock on cancel, email dispatch).
- `api/orders.py` and `api/carts.py` parse requests, resolve auth, call services, serialize responses. No business logic.
- `services/inventory.py` is the only place that reads/writes `StoreInventory.stock` for order flows. Other features that touch inventory continue to use the existing `api/stores.py` paths.
- Frontend `CartContext` is the only consumer of `localCart`/`remoteCart`. UI components call context methods, never the adapters directly.
- Frontend `lib/orders.ts` is the only place that talks to `/api/v1/orders/*`. Pages call it; components receive data via props.

## Data Flow

### Cart sync on login

1. Guest browses, adds items. `localStorage.kb_carts` holds carts grouped by `store_id`. Each cart item now carries `{product_id, inventory_id, product_name, price, quantity}` (frontend `CartItem` extended with `inventory_id`).
2. User completes OTP login. JWT cookie set.
3. `CartContext` observes auth transition. If `localStorage` has any carts, it calls `POST /api/v1/carts/sync {carts: [...]}`.
4. Backend, per cart in payload:
   - Upsert `Cart(customer_profile_id, store_id)`.
   - For each item, upsert `CartItem(cart_id, inventory_id)` with `quantity = existing + payload.quantity` (sum on conflict, no data loss).
   - Drop items whose `inventory_id` no longer resolves; include them in the response under `dropped: [...]`.
5. Backend returns the full DB cart state.
6. Frontend clears `localStorage`, sets context state from response.
7. Subsequent cart edits go straight to the API.

### Cart edit while logged in

1. UI calls `cartContext.addItem({store_id, inventory_id, quantity})`.
2. Context updates local React state immediately (optimistic).
3. Context calls `POST /api/v1/carts/items` in background.
4. On success: response replaces optimistic state with canonical.
5. On failure: rollback local state, show toast.

### Checkout

1. Customer is on `/cart`, logged in, has at least one saved address. UI shows `<AddressPicker />` (defaults to first address) and an enabled "Place Order" button.
2. Tap fires `POST /api/v1/orders {address_id}`.
3. Backend `place_orders_from_cart()` runs in a single transaction:
   1. Resolve the incoming `customer_address_id` to a `CustomerAddress` row owned by the current customer; pull its `address_id` (the underlying `Address` FK) and a formatted snapshot string.
   2. Load `Cart` rows for the customer joined with `CartItem` and `StoreInventory`. Lock inventory rows with `SELECT ... FOR UPDATE` to serialize concurrent checkouts.
   3. Validate: cart is non-empty, every item has `StoreInventory.stock >= ordered_qty`, every item still resolves and has `is_available=True`, every store is `is_active=True`. Snapshot current `StoreInventory.price` as the unit price.
   4. For each store cart:
      - Compute `subtotal = sum(unit_price * quantity)`. `delivery_fee` = flat ₹0 for MVP (placeholder, easily configured later). `tax = 0`. `total = subtotal + delivery_fee + tax`.
      - Insert `Order(status=Pending, customer_profile_id, store_id, delivery_address_id, delivery_address_snapshot, subtotal, delivery_fee, tax, total, placed_at=now())`.
      - Insert `OrderItem` rows with `product_name_snapshot` and `unit_price_snapshot` captured.
      - Decrement `StoreInventory.stock` by ordered amount.
      - Insert `Payment(order_id, amount=total, method=Cash, status=Pending)`.
      - Insert `Delivery(order_id, status=Pending)`.
   5. Delete the customer's `Cart` rows along with their `CartItem` rows (delete items first, then carts).
   6. Commit.
4. After commit, dispatch Celery tasks: one `send_order_placed_seller_async(order_id)` per order, plus a single `send_order_confirmed_customer_async(order_ids=[...])`.
5. Response: `{orders: [{id, store_id, status, total, ...}]}`.
6. Frontend redirects to `/account/orders` and toasts "N orders placed".

### Status transition

1. Seller views order detail at `/seller/orders/{id}`. Status is `Pending`. UI shows "Mark Packed" button.
2. Tap fires `POST /api/v1/orders/{id}/transition {to: "packed"}`.
3. Backend `transition_order_status()`:
   1. Load order with payment + delivery.
   2. Verify caller owns the store (or is admin).
   3. Verify the transition is legal per the state machine below.
   4. Update `Order.status`. Update `Delivery` timestamps (`packed_at`, `dispatched_at`, `delivered_at`) for the matching transition.
   5. If transitioning to `Delivered`: also set `Payment.status = Paid` and `Payment.paid_at = now()`. (Note: `Delivered` here means delivered AND cash collected. UI confirms before firing.)
   6. Commit.
   7. Dispatch `send_order_status_changed_async(order_id, new_status)` to email the customer.
4. Response: updated order.

### Cancellation

1. Caller fires `POST /api/v1/orders/{id}/cancel`.
2. Backend `cancel_order()`:
   1. Load order.
   2. Authorize per role:
      - Customer: only if `status == Pending`.
      - Seller: only if `status not in (Delivered, Cancelled)` and seller owns the store.
      - Admin: only if `status not in (Delivered, Cancelled)`.
   3. Update `Order.status = Cancelled`, `Delivery.status = Cancelled`.
   4. If `Payment.status == Paid`: set `Payment.status = Refunded`. Otherwise leave `Pending`. (For COD this only matters if a Delivered order is later cancelled, which only admin can do.)
   5. For each `OrderItem`, increment `StoreInventory.stock` by `OrderItem.quantity` (restock).
   6. Commit.
   7. Dispatch `send_order_status_changed_async(order_id, "cancelled")` for the customer AND `send_order_placed_seller_async`-style notification to the seller (re-using one task that takes a recipient hint, or two separate dispatch calls). Both parties get notified.

### Active orders fetch

- `GET /api/v1/orders?status=active` for the current user's role.
  - Customer sees their orders.
  - Seller sees orders where `store_id` is in their owned stores.
  - Admin sees all.
- `active = status IN (Pending, Packed, Dispatched)`.
- `history = status IN (Delivered, Cancelled)`.
- Dashboard widget polls every 15 seconds with `setInterval`. Manual refresh button available.

### Order state machine

```
Pending     → Packed | Cancelled
Packed      → Dispatched | Cancelled
Dispatched  → Delivered | Cancelled
Delivered   → (terminal)
Cancelled   → (terminal)
```

Cancellation actor restrictions enforced separately in `cancel_order()`.

**Note on `OrderStatus.Paid`:** the `OrderStatus` enum in `models/commerce.py` includes a `Paid` value from earlier schema work. The fulfillment lifecycle does NOT use it — `Order.status` only tracks fulfillment, and `Payment.status` is the authoritative source for payment state. `transition_order_status()` rejects any target outside `{Packed, Dispatched, Delivered}`, so `Paid` is unreachable. Treat the enum value as legacy; do not write it. (A future cleanup migration may remove it.)

## API Surface

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/carts` | Customer | List all carts for current user |
| `POST` | `/api/v1/carts/items` | Customer | Add item `{store_id, inventory_id, quantity}` |
| `PATCH` | `/api/v1/carts/items/{id}` | Customer (owns) | Update qty `{quantity}` |
| `DELETE` | `/api/v1/carts/items/{id}` | Customer (owns) | Remove single item |
| `DELETE` | `/api/v1/carts/{store_id}` | Customer | Clear store cart |
| `POST` | `/api/v1/carts/sync` | Customer | Bulk merge `{carts: [...]}` from localStorage |
| `POST` | `/api/v1/orders` | Customer | Place orders from DB cart `{customer_address_id}` |
| `GET` | `/api/v1/orders` | Customer / Seller / Admin | List, scoped by role; `?status=active\|history` |
| `GET` | `/api/v1/orders/{id}` | Customer (owns) / Seller (owns store) / Admin | Order detail |
| `POST` | `/api/v1/orders/{id}/transition` | Seller (owns store) / Admin | `{to: "packed"\|"dispatched"\|"delivered"}` |
| `POST` | `/api/v1/orders/{id}/cancel` | Customer (Pending only) / Seller (pre-Delivered) / Admin | No body |

### New auth dependency

`get_current_customer(...)` added alongside the existing `get_current_seller` (`backend/app/src/app/api/sellers.py:40`) and `get_current_admin`. Returns `User` if role is Customer, raises 403 otherwise.

### Pydantic schemas (sketch)

```python
class OrderItemRead(BaseModel):
    id: int
    inventory_id: int | None
    product_name_snapshot: str
    unit_price_snapshot: float
    quantity: int
    line_total: float

class PaymentRead(BaseModel):
    method: PaymentMethod
    status: PaymentStatus
    amount: float
    paid_at: datetime | None

class DeliveryRead(BaseModel):
    status: DeliveryStatus
    packed_at: datetime | None
    dispatched_at: datetime | None
    delivered_at: datetime | None

class OrderRead(BaseModel):
    id: int
    store_id: int
    store_name: str
    customer_name: str | None  # only populated for seller/admin views
    status: OrderStatus
    subtotal: float
    delivery_fee: float
    tax: float
    total: float
    placed_at: datetime
    delivery_address_snapshot: str
    items: list[OrderItemRead]
    payment: PaymentRead
    delivery: DeliveryRead

class PlaceOrderRequest(BaseModel):
    customer_address_id: int   # CustomerAddress.id, resolved server-side to Address.id

class TransitionRequest(BaseModel):
    to: Literal["packed", "dispatched", "delivered"]
```

## Database Changes

`Order`, `OrderItem`, `Payment`, `Delivery`, `Cart`, and `CartItem` all already exist and need no field renames. One migration adds:

1. Composite index `ix_order_store_status` on `order(store_id, status)` — speeds up seller dashboard queries.
2. Composite index `ix_order_customer_status` on `order(customer_profile_id, status)` — speeds up customer dashboard queries.
3. New non-null column `order.delivery_address_snapshot text` — denormalized formatted address so order history survives address deletion.
4. Change `orderitem.inventory_id` foreign key to `ON DELETE SET NULL` — keeps history readable if a seller pulls an inventory row. `product_name_snapshot` and `unit_price_snapshot` already preserve display data.

## Frontend Pages and Components

### Customer

- `/account/page.tsx` — existing landing. Add `<ActiveOrdersWidget role="customer" limit={5} />` near the top with a "View all" link.
- `/account/orders/page.tsx` — tabs for Active and History. Each tab is a list of `<OrderCard />`s grouped by `placed_at` date. Empty state for both.
- `/account/orders/[id]/page.tsx` — `<OrderTimeline />` at top, `<OrderItemList />`, payment summary, delivery address, store contact link. "Cancel order" button visible only if `status == Pending`.

### Seller

- `/seller/page.tsx` — existing dashboard. Add `<ActiveOrdersWidget role="seller" limit={10} />` as the primary section.
- `/seller/orders/page.tsx` — tabs for Active and History. Each `<OrderCard />` shows customer name and inline action button for the next legal transition.
- `/seller/orders/[id]/page.tsx` — full detail. `<OrderActionButtons role="seller" />` shows the next transition button (Mark Packed → Mark Dispatched → Mark Delivered) and a "Cancel" button. "Mark Delivered" opens a confirm dialog: "Cash collected from customer?".

### Admin

- `/admin/page.tsx` — landing (create if absent, otherwise extend). Add `<ActiveOrdersWidget role="admin" limit={10} />`.
- `/admin/orders/page.tsx` — full platform list. Filter controls: store, status, date range. Read-only `<OrderCard />`s.
- `/admin/orders/[id]/page.tsx` — read-only detail. Single "Cancel order" button if order is not terminal. No transition controls.

### Cart page changes (`/cart/page.tsx`)

- Replace the disabled checkout button + tooltip with conditional state:
  - Guest: button text "Login to checkout" → navigates to `/login?next=/cart`.
  - Logged in, no addresses: "Add address to checkout" → navigates to `/account/settings`.
  - Logged in, has addresses: enabled "Place Order" button.
- Add `<AddressPicker />` above the totals block. Loads from `/api/v1/customers/me/addresses` (existing endpoint). Defaults to first address.
- On click: `POST /api/v1/orders {address_id}`. On success: redirect `/account/orders` with toast. On 409 stock/price errors: re-fetch cart, highlight problematic items, ask user to confirm.

### Shared components

```
components/orders/
├── ActiveOrdersWidget.tsx   # polling list, role-aware fetch + render
├── OrderCard.tsx            # compact row: store/customer, total, status badge, time-ago
├── OrderTimeline.tsx        # vertical timeline: Pending → Packed → Dispatched → Delivered (greyed steps for cancelled)
├── OrderStatusBadge.tsx     # color-coded pill
├── OrderItemList.tsx        # reused on detail pages
├── OrderActionButtons.tsx   # role-aware: transition (seller), cancel (all), nothing (read-only)
└── AddressPicker.tsx        # used on cart page only
```

### Cart context refactor

`lib/cart.ts` shrinks to shared types and pure helpers (`getCartTotal`, `getGrandTotal`, `getCartCount`). Two new adapters:

- `lib/localCart.ts` — current `localStorage` logic moved here.
- `lib/remoteCart.ts` — typed API client matching the cart endpoints in §API Surface.

`lib/CartContext.tsx`:

```ts
const { user } = useAuth();
const backend = user ? remoteCart : localCart;

useEffect(() => {
  if (user && hasLocalCarts()) {
    syncLocalToRemote().then(clearLocal).then(refresh);
  } else if (user) {
    refresh();
  }
}, [user?.id]);
```

All cart mutations exposed by context become `async`. Optimistic state update inside the context; on API error, rollback and toast.

### Type additions (`types/index.ts`)

```ts
export type OrderStatus = "pending" | "packed" | "dispatched" | "delivered" | "cancelled";
export type PaymentStatus = "pending" | "paid" | "failed" | "refunded";
export type DeliveryStatus = "pending" | "packed" | "dispatched" | "delivered" | "cancelled";

export interface OrderItem {
  id: number;
  inventory_id: number | null;
  product_name_snapshot: string;
  unit_price_snapshot: number;
  quantity: number;
  line_total: number;
}

export interface Order {
  id: number;
  store_id: number;
  store_name: string;
  customer_name?: string;
  status: OrderStatus;
  subtotal: number;
  delivery_fee: number;
  tax: number;
  total: number;
  placed_at: string;
  delivery_address_snapshot: string;
  items: OrderItem[];
  payment: { method: string; status: PaymentStatus; amount: number; paid_at: string | null };
  delivery: { status: DeliveryStatus; packed_at: string | null; dispatched_at: string | null; delivered_at: string | null };
}
```

`CartItem` extended: add `inventory_id: number` alongside `product_id`. All add-to-cart call sites must pass it from inventory listing responses.

### Navigation

- Customer navbar (when logged in as Customer): "Orders" → `/account/orders`.
- Seller layout sidebar: "Orders" → `/seller/orders`.
- Admin layout sidebar: "Orders" → `/admin/orders`.

## Celery Tasks

Three tasks added to `backend/app/src/app/worker.py`:

```python
@celery_app.task(autoretry_for=(Exception,), max_retries=3, retry_backoff=True)
def send_order_placed_seller_async(order_id: int) -> None: ...

@celery_app.task(autoretry_for=(Exception,), max_retries=3, retry_backoff=True)
def send_order_confirmed_customer_async(order_ids: list[int]) -> None: ...

@celery_app.task(autoretry_for=(Exception,), max_retries=3, retry_backoff=True)
def send_order_status_changed_async(order_id: int, new_status: str) -> None: ...
```

Each task opens a fresh DB session, loads the order(s), renders an email, and sends via Resend (reusing the pattern at `worker.py:14`). Tasks dispatched only after the parent transaction commits. Email failures are logged and retried; they never block the order.

## Errors and Edge Cases

### Checkout (`POST /orders`)

| Condition | HTTP | Body |
|---|---|---|
| Empty cart | 400 | `{detail: "cart_empty"}` |
| Address not owned | 403 | `{detail: "invalid_address"}` |
| Inventory insufficient | 409 | `{detail: "insufficient_stock", item: {inventory_id, available_stock, requested}}` |
| Price changed since cart add | 409 | `{detail: "price_changed", items: [...]}` |
| Inventory unavailable (deleted or `is_available=False`) | 409 | `{detail: "item_unavailable", inventory_ids: [...]}` |
| Store inactive (`is_active=False`) | 409 | `{detail: "store_unavailable", store_id}` |

All checkout failures fully roll back. No partial orders, no partial stock decrements.

### Status transition

| Condition | HTTP |
|---|---|
| Not seller of store and not admin | 403 |
| Illegal transition | 409 `{detail: "illegal_transition", from, to}` |
| Order already terminal | 409 `{detail: "terminal_status"}` |

### Cancel

| Condition | HTTP |
|---|---|
| Customer cancelling non-Pending order | 403 `{detail: "cancel_not_allowed"}` |
| Already terminal | 409 `{detail: "terminal_status"}` |

### Cart sync conflicts

Quantities sum on conflict. Items whose `inventory_id` no longer resolves are silently dropped from sync; response includes `{synced: [...], dropped: [{inventory_id, reason}]}` so the UI can toast a warning.

### Concurrency

Two customers checkout the same item at the same time. The checkout transaction acquires `SELECT ... FOR UPDATE` row locks on involved `StoreInventory` rows in a deterministic order (sorted by id) to avoid deadlocks. The second writer sees insufficient stock and gets a 409.

### Email failures

Order is committed before any Celery dispatch. Email tasks have their own retry (`autoretry_for=(Exception,), max_retries=3, retry_backoff=True`). A failed email never blocks an order or a transition.

### Logout mid-edit

Optimistic cart updates may have an in-flight request when the user logs out. Discard the queue and clear local state on logout transition.

### Concurrent cart edits across devices

Last-write-wins per item. Optimistic UI on device A may briefly show a stale qty until the next refresh. Acceptable for MVP.

### Cash collection at delivery

`Delivered` is terminal in the schema. UX safeguard: "Mark Delivered" opens a confirm dialog reading "Cash collected from customer?" before firing the transition. If the seller cannot collect, they cancel instead (which they are allowed to do pre-Delivered).

### Address deleted after order placed

Resolved by writing `delivery_address_snapshot` (formatted address text) into the `Order` row at placement time. The FK is kept for joins when the address still exists.

### Inventory deleted after order placed

Resolved by changing `orderitem.inventory_id` to `ON DELETE SET NULL`. `product_name_snapshot` and `unit_price_snapshot` already preserve display fields.

### Pagination

Active orders are bounded (in-flight). History is capped at the last 50 orders per role view for MVP. Pagination UI is not in scope.

## Testing

Backend tests against the existing `khanabazaar_test` Postgres database, following the override pattern in `backend/app/tests/conftest.py` and `backend/app/tests/test_stores.py`.

`backend/app/tests/test_carts.py`:

- Add item to cart, returns canonical row.
- Update qty, remove item, clear store cart.
- `POST /carts/sync` with empty payload returns empty.
- `POST /carts/sync` with overlapping items merges by summing quantities.
- `POST /carts/sync` drops items whose `inventory_id` does not resolve.
- Customer A cannot read or modify customer B's cart (403).

`backend/app/tests/test_orders.py`:

- Happy path: place order from a multi-store cart fans out to N `Order`s, all `OrderItem`s created with snapshots, `Payment` and `Delivery` created, stock decremented, cart cleared.
- Empty cart returns 400.
- Address not owned returns 403.
- Insufficient stock returns 409, no rows written, no stock change.
- Price drift returns 409.
- Concurrent checkout race (two `asyncio.gather` calls placing the same item): exactly one succeeds, other gets 409.
- Status transitions: legal sequence per role, illegal returns 409.
- Marking Delivered also flips `Payment.status = Paid` and sets `paid_at`.
- Customer can cancel only `Pending`; seller can cancel pre-`Delivered`; admin can cancel any non-terminal. Each cancel restocks the right amount.
- Seller can only see and transition orders for their own stores (403 otherwise).
- Customer can only see their own orders.
- Admin can see all and cancel any non-terminal.

`backend/app/tests/test_order_emails.py`:

- Mock Resend; verify each of the three task functions dispatches with correct arguments at the right lifecycle points.

Frontend testing is out of scope (no framework set up). Document a manual test checklist in the PR for: cart sync on login, optimistic update rollback on API failure, multi-store checkout, address picker, role-specific dashboards, status transitions, cancel rules, polling refresh.

## Migrations

Single Alembic migration:

1. Create composite index `ix_order_store_status` on `order(store_id, status)`.
2. Create composite index `ix_order_customer_status` on `order(customer_profile_id, status)`.
3. Add column `order.delivery_address_snapshot text NOT NULL` (with a server default of empty string for any preexisting test data, then drop the default).
4. Alter `orderitem.inventory_id` foreign key to `ON DELETE SET NULL`.

## Open Questions

None. All scope decisions confirmed during brainstorm: COD-only payment, atomic single-button fan-out checkout, decrement-with-restock-on-cancel, full status chain, login + saved address gate, Celery emails to both parties, admin read-all + cancel-override, DB-backed cart for logged-in users with localStorage sync on login, polling for dashboard freshness.
