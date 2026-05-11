<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Per-store-per-service checkout: sub-basket split

**Date:** 2026-05-10
**Status:** Draft — awaiting user review

## Goal

A customer can hold items from multiple services (Grocery, Pharmacy, Food, …) at the same store, but each order ships items from **exactly one service**. Promote the existing per-store cart into a per-store-per-service cart ("sub-basket"). Each sub-basket checks out as its own order; sibling sub-baskets stay intact.

## Decisions locked during brainstorming

| Topic | Decision |
|---|---|
| Cross-service add behavior | Auto-split into sub-baskets — no modal, no warning. |
| Checkout granularity | One sub-basket per order. Sibling sub-baskets untouched after placement. |
| Data model | Promote `Cart` to `(customer_profile_id, store_id, service_id)`. `Order` gains `service_id` + `service_name_snapshot`. |
| Cart UX | Store cards with one section per service inside. Single-service stores render without service header. |
| Migration | Pre-launch full nuke of `cart`, `cartitem`, `order`, `orderitem`, `payment`, `delivery`, `review`. |
| Service name in order | Snapshot at placement time (English `ServiceTranslation` with slug fallback). |
| Catalog drift | 409 `service_mismatch` at checkout; customer removes offending item. No auto-purge. |
| Seller revokes a service | No automatic cart purge. Customer learns at checkout via 409 `service_unavailable`. |

## 1. Data model

### `Cart`
```python
class Cart(BaseSchema, table=True):
    __table_args__ = (
        UniqueConstraint(
            "customer_profile_id", "store_id", "service_id",
            name="uq_cart_customer_store_service",
        ),
    )
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False)
    store_id: int          = Field(foreign_key="store.id",            nullable=False)
    service_id: int        = Field(foreign_key="service.id",          nullable=False, index=True)
```
- `service_id` is NOT NULL.
- The old `uq_cart_customer_store` constraint is dropped.
- No SQLModel `Relationship()` to Service — never traversed in code.

### `CartItem`
Unchanged. Service identity lives on the parent Cart row, derivable per item via `inventory → product → subcategory → category.service_id`.

### `Order`
```python
class Order(BaseSchema, table=True):
    ...
    service_id: int                    = Field(foreign_key="service.id", nullable=False, index=True)
    service_name_snapshot: str         = Field(nullable=False)
    ...
```
- `service_name_snapshot` is frozen at placement time — display-safe even after rename or translation removal.
- `OrderItem` unchanged.

### Invariant
Every CartItem's inventory must resolve to its parent Cart's `service_id`. Enforced as a service-layer check at both cart-add and order-placement. A DB-level CHECK is not added — keeping the assertion in application code matches existing patterns (`_validate_inventory_availability`, `_validate_stores_active`).

## 2. Backend — cart API (`backend/app/src/app/api/carts.py` + `schemas/carts.py`)

### Schema additions
- `CartRead`: + `service_id: int`, `service_name: str`.
- `CartItemAdd`: + `service_id: int`.
- `CartSyncCart`: + `service_id: int`.
- `DroppedSyncItem.reason`: new value `"service_mismatch"`.

### Route changes

| Route | Before | After |
|---|---|---|
| `GET /` | one row per `(profile, store)` | one row per `(profile, store, service)`; `service_id` + `service_name` (via `ServiceTranslation(en)` join, slug fallback) included. |
| `POST /items` | body `{store_id, inventory_id, quantity}` | body `{store_id, service_id, inventory_id, quantity}`. Two-pronged validation (see below). `_get_or_create_cart` signature becomes `(profile_id, store_id, service_id)`. |
| `PATCH /items/{id}` | unchanged | unchanged |
| `DELETE /items/{id}` | unchanged | unchanged — when last item removed, parent Cart row deleted as today. |
| `DELETE /{store_id}` | clears whole store cart | replaced by `DELETE /{store_id}/{service_id}` — clears one sub-basket. No back-compat shim (pre-launch). |
| `POST /sync` | body `[{store_id, items[]}]` | body `[{store_id, service_id, items[]}]`. Per-entry validation: items whose inventory resolves to a different service fall into `dropped[]` with `reason="service_mismatch"`. |

### Two-pronged cart-add validation
At `POST /items` and inside `POST /sync` per entry:

1. **Store offers this service.** Resolve the store's seller via `Store.seller_profile_id`, check `SellerProfileService(seller_profile_id, service_id)` exists, AND check `Service(service_id).is_active = true`. If either fails → 409 `service_unavailable`.
2. **Inventory's product belongs to this service.** Run the live join `StoreInventory → MasterProduct → Subcategory → Category.service_id` and compare to `payload.service_id`. If mismatched → 400 `service_mismatch` (for sync, falls into `dropped[]` instead of returning error).

Existing checks (`inventory_store_mismatch`, `item_unavailable`) run first.

## 3. Backend — orders API (`backend/app/src/app/api/orders.py` + `schemas/orders.py`)

### Schema additions
- `OrderRead`: + `service_id: int`, + `service_name: str` (sourced from `Order.service_name_snapshot`).
- `PlaceOrderRequest`: + `service_id: int = Field(gt=0)`.

### Route changes

| Route | Change |
|---|---|
| `POST /` | Payload requires `service_id`. Handler calls renamed `place_order_for_sub_basket(...)`. |
| `GET /` (customer + seller) | Response per-order gains `service_id` + `service_name`. Customer list keeps existing `?store_id=` filter and adds optional `?service_id=` (cheap WHERE). Seller list adds the fields but does not gain a service filter in this spec. |
| `GET /{id}` | Response gains `service_id` + `service_name`. |
| `POST /{id}/transition`, `/cancel` | Unchanged — service is immutable post-placement. |

## 4. Backend — checkout service (`backend/app/src/app/services/checkout.py`)

### Renames + new helpers
- `place_order_for_store(session, user, customer_address_id, store_id, payment_method)` →
  `place_order_for_sub_basket(session, user, customer_address_id, store_id, service_id, payment_method)`.
- `_load_cart_for_store(profile_id, store_id)` → `_load_cart_for_sub_basket(profile_id, store_id, service_id)`. Returns the single Cart row; 404 `cart_not_found` if none, 400 `cart_empty` if no items.
- New `_validate_service_active_for_store(session, store_id, service_id)`:
  - Joins `Store → SellerProfile → SellerProfileService`. Asserts a row exists.
  - Asserts `Service.is_active = true`.
  - 409 `{"detail":"service_unavailable", "store_id":..., "service_id":...}` on failure.
- New invariant assertion: after `lock_inventory_rows`, run the live join from each locked inventory to `Category.service_id`. If any resolved service ≠ `service_id` → 409 `{"detail":"service_mismatch","inventory_id":...}`, roll back locks.
- `_build_order_for_cart` writes `order.service_id = cart.service_id` and `order.service_name_snapshot = <en name or slug>` (helper mirrors `_snapshot_product_names`).
- Cart cleanup deletes **only the one** sub-basket's Cart row and its items. Sibling sub-baskets for the same store remain.

### Order email side-effect (`services/order_emails.py`)
- Order-placed and status-change templates include the service name in the subject and body (e.g. `Order #123 · Grocery · packed`). Sourced from `Order.service_name_snapshot` to avoid extra joins. Without this, customers with multiple same-day sub-basket orders cannot disambiguate at a glance.

### Error map (additions in **bold**)

| Code | Status | Detail |
|---|---|---|
| `cart_not_found` | 404 | unchanged — now per sub-basket |
| `cart_empty` | 400 | unchanged |
| **`service_unavailable`** | 409 | seller revoked or service globally inactive |
| **`service_mismatch`** | 400 / 409 | 400 on cart-add (payload→inventory mismatch), 409 on checkout (catalog drift) |
| `store_unavailable` | 409 | unchanged |
| `invalid_address` | 403/404 | unchanged |
| `item_unavailable` | 409 | unchanged |
| `insufficient_stock` | 409 | unchanged |

## 5. Frontend — types + cart layer

### `src/types/index.ts`
```ts
interface Cart {
  store_id: number;
  store_name: string;
  service_id: number;     // new
  service_name: string;   // new
  items: CartItem[];
}

interface Order {
  ...
  service_id: number;     // new
  service_name: string;   // new
}
```
`CartItem` unchanged.

### `src/lib/localCart.ts` (guest cart)
- Storage key bumps `kb_carts` → `kb_carts_v2`.
- On first read post-upgrade: `localStorage.removeItem("kb_carts")` once (orphan cleanup), then continue with v2 only.
- Lookup keys composite — `${storeId}:${serviceId}`.
- All mutators take `serviceId` (and `serviceName` for `addToCart`) as required args:
  - `addToCart(storeId, storeName, serviceId, serviceName, item)`
  - `removeFromCart(storeId, serviceId, productId)`
  - `updateQuantity(storeId, serviceId, productId, qty)`
  - `clearCart(storeId, serviceId)`
- Cross-service "auto-split" is automatic — adding from a different service produces a new sub-basket row, not a conflict.

### `src/lib/remoteCart.ts` + `src/lib/CartContext.tsx`
- Sync payload (`POST /carts/sync`) sends `service_id` per cart entry.
- `clearStoreCart(token, storeId)` → `clearSubBasket(token, storeId, serviceId)` and points at `DELETE /carts/{store_id}/{service_id}`.
- All mutator signatures gain `serviceId` (and `serviceName` where needed). `findRemoteItemId` keys on `(storeId, serviceId, productId)`.

## 6. Frontend — UI

### `/cart` page
- Outer loop: group `carts[]` by `store_id`. One card per store.
- Inner loop: each sub-basket renders as a section.
  - Section header: service name + item count.
  - Items list, qty steppers, line totals.
  - Section footer: subtotal + `Checkout {ServiceName}` button → `/checkout/{storeId}/{serviceId}`.
- Single-service store: suppress service header, keep service-named checkout button.
- Empty state, sync-dropped banner, grand-total math — unchanged, just summed over sub-baskets.

### `/checkout/[storeId]/` → `/checkout/[storeId]/[serviceId]/`
- New dynamic segment. Page loads the single sub-basket for `(storeId, serviceId)`, the customer's addresses, and the store's serviceability info.
- On 200, route to `/account/orders/{id}`.
- On 409 `service_unavailable` / `service_mismatch`, toast and bounce to `/cart` so other sub-baskets stay visible.

### Product-add entry points
- `ProductCard` / store-detail page reads `service_id` from the active service in the store-detail sidebar data (already loaded). Passes `(serviceId, serviceName)` down to the add-to-cart call. No extra fetch.

### Order list / detail
- Order header chip displays `{Store} · {Service}`.
- No list-level service filter UI in this spec — backend field is exposed for a future task.

## 7. Migration (single Alembic revision)

```python
def upgrade() -> None:
    # 1. Wipe transactional data — pre-launch.
    op.execute(
        "TRUNCATE TABLE review, payment, delivery, orderitem, \"order\", "
        "cartitem, cart RESTART IDENTITY CASCADE"
    )

    # 2. Cart schema
    op.drop_constraint("uq_cart_customer_store", "cart", type_="unique")
    op.add_column("cart", sa.Column("service_id", sa.Integer(), nullable=False))
    op.create_foreign_key(
        "fk_cart_service", "cart", "service", ["service_id"], ["id"],
    )
    op.create_index("ix_cart_service_id", "cart", ["service_id"])
    op.create_unique_constraint(
        "uq_cart_customer_store_service", "cart",
        ["customer_profile_id", "store_id", "service_id"],
    )

    # 3. Order schema
    op.add_column("order", sa.Column("service_id", sa.Integer(), nullable=False))
    op.add_column("order", sa.Column("service_name_snapshot", sa.String(), nullable=False))
    op.create_foreign_key(
        "fk_order_service", "order", "service", ["service_id"], ["id"],
    )
    op.create_index("ix_order_service_id", "order", ["service_id"])


def downgrade() -> None:
    op.execute(
        "TRUNCATE TABLE review, payment, delivery, orderitem, \"order\", "
        "cartitem, cart RESTART IDENTITY CASCADE"
    )
    op.drop_index("ix_order_service_id", "order")
    op.drop_constraint("fk_order_service", "order", type_="foreignkey")
    op.drop_column("order", "service_name_snapshot")
    op.drop_column("order", "service_id")
    op.drop_constraint("uq_cart_customer_store_service", "cart", type_="unique")
    op.drop_index("ix_cart_service_id", "cart")
    op.drop_constraint("fk_cart_service", "cart", type_="foreignkey")
    op.drop_column("cart", "service_id")
    op.create_unique_constraint(
        "uq_cart_customer_store", "cart", ["customer_profile_id", "store_id"],
    )
```

- `review` listed explicitly because `Review.order_id` is a nullable FK to `order`; Postgres `TRUNCATE … CASCADE` would propagate anyway, but the explicit list documents intent. `Favorite` references `masterproduct`, not order/cart — safe to omit.
- `RESTART IDENTITY` resets the sequence on each truncated table.
- `db/seed.py` updated: any sample carts/orders set `service_id` + `service_name_snapshot` explicitly. No-op if no demo orders exist.

## 8. Seller-side ramifications

- `PATCH /sellers/me/profile` and `PATCH /sellers/admin/{seller_id}/services` already use `replace_profile_services`. No granular DELETE-per-service endpoint exists, so revoking a service in the dashboard happens via the bulk replace. This spec does **not** add auto-purge of customers' carts when a service is removed from a seller's approved list. The customer's stale sub-basket fails at checkout with 409 `service_unavailable` and the customer manually adjusts. Auto-purge needs a background job and customer messaging — out of scope.
- Seller orders list (`GET /orders` with seller role) exposes the new `service_id` + `service_name` fields. A "Pharmacy queue" UI for sellers is out of scope.

## 9. Testing

### New backend tests
- `tests/test_carts_per_service.py`
  - Store offers Grocery + Pharmacy; customer adds one Grocery item + one Pharmacy item → `GET /carts/` returns two rows for that store, distinct `service_id`s.
  - `POST /carts/items` with `service_id` not in the store's offered services → 409 `service_unavailable`.
  - `POST /carts/items` with `service_id` mismatching the inventory's derived service → 400 `service_mismatch`. No cart row created.
  - `POST /carts/items` for a globally inactive `Service` → 409 `service_unavailable`.
  - `DELETE /carts/{store_id}/{service_id}` clears one sub-basket; sibling untouched.
  - `POST /carts/sync` with mixed-service items per entry filters mismatches into `dropped[]` with `reason="service_mismatch"`.

- `tests/test_orders_per_service.py`
  - Place order from Grocery sub-basket → sibling Pharmacy sub-basket survives; new Order has `service_id` and `service_name_snapshot` set.
  - Place order with `service_id` not on `SellerProfileService` → 409 `service_unavailable`. Cart untouched, inventory locks released.
  - Catalog drift after add-to-cart (admin moves product to another service) → 409 `service_mismatch` at checkout. Locks released.
  - `GET /orders/?service_id=X` filters customer's orders correctly; `?store_id=` filter still works alongside.
  - `service_name_snapshot` falls back to slug when no `ServiceTranslation("en")` exists.

### Updated backend tests
- `tests/test_checkout.py` — every call now passes `service_id` in payload. The `place_order_for_store` → `place_order_for_sub_basket` rename touches imports.
- `tests/test_carts.py` — payloads gain `service_id`; expected response shape includes `service_id` + `service_name`.

### Frontend manual verification
No frontend test suite exists per CLAUDE.md. Manual checks:
- Add Grocery → add Pharmacy from same store → `/cart` shows one store card with two sections.
- Click "Checkout Grocery" → land on `/checkout/{storeId}/{groceryServiceId}` → place order → `/cart` now shows only Pharmacy section for that store.
- Single-service store renders without the service header but with the per-service checkout button.
- Guest-to-logged-in sync: guest cart with two sub-baskets per store survives login.
- Order email subject includes service name.

## 10. Out of scope

- Bundled multi-sub-basket checkout (one shared address + payment, N orders created).
- Auto-purge of customer carts when a seller drops a service.
- Seller dashboard service-segmented order queues.
- Catalog-drift auto-resolution (currently the customer must remove the offending item on 409).
- Multi-language service names — snapshot is English only, matching existing product/service handling.
- Per-service delivery fees or tax. MVP values stay 0.

## 11. Files touched (rough inventory)

**Backend**
- `models/commerce.py` — Cart, Order field additions
- `migrations/versions/<new>.py` — schema migration
- `services/checkout.py` — rename + sub-basket loader + service validation
- `services/orders.py` — read-path serialization of new fields
- `services/order_emails.py` — service name in subject/body
- `api/carts.py` — route changes, 2-pronged validation, `_get_or_create_cart` signature
- `api/orders.py` — route + payload changes + `?service_id=` filter
- `schemas/carts.py`, `schemas/orders.py` — DTO updates
- `db/seed.py` — set `service_id` on any demo carts/orders
- `tests/test_carts.py`, `test_orders.py`, `test_checkout.py` updated; two new files.

**Frontend**
- `types/index.ts` — Cart + Order field additions
- `lib/localCart.ts` — composite key + arg signatures + `kb_carts_v2`
- `lib/remoteCart.ts` — sync payload, clear-cart URL
- `lib/CartContext.tsx` — mutator signatures, `clearSubBasket`
- `app/(customer)/[locale]/cart/page.tsx` — store-card + sub-basket sections
- `app/(customer)/[locale]/checkout/[storeId]/` → `[storeId]/[serviceId]/`
- `components/ProductCard` and store-detail add-to-cart call sites — pass `serviceId`/`serviceName`
- `app/(customer)/[locale]/account/orders/...` — service chip in header

**Docs**
- `docs/flows.md` — replace per-store-checkout section with per-store-per-service-checkout.
- `CLAUDE.md` — update Cart unique key, Order column list, per-store-checkout pattern bullet.
