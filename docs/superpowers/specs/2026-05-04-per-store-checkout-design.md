<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Per-Store Checkout Design

**Date:** 2026-05-04
**Status:** Approved (pre-implementation)

## Problem

Today, `/cart` lists items grouped by store and a single "Place Order" button creates one Order per store in a single transaction (`place_orders_from_cart` in `backend/app/src/app/services/checkout.py`). The user wants checkout to be per-store: a customer must explicitly check out one store at a time, picking a payment method as part of that flow. Carts for other stores must remain untouched.

## Goals

- A customer with carts at N stores can check out exactly one store per submission.
- The customer chooses a payment method (UPI or Cash) as part of checkout.
- The flow is shaped so a future Razorpay (or similar gateway) integration can replace the UPI path without UI rework.
- Carts for stores not being checked out are preserved across the operation.

## Non-Goals

- Real payment gateway integration (Razorpay, PhonePe, UPI intent). UPI is a label only; `Payment.status` stays `Pending` and is flipped manually downstream.
- Per-store delivery fees / GST. Existing `MVP_DELIVERY_FEE = 0` and `MVP_TAX = 0` constants stay.
- Multi-address-per-store checkout (the customer picks one address per checkout submission, which the backend already snapshots per Order).
- Changes to inventory locking, order state transitions, or order email behavior.
- Live polling of stock or carts. Validation happens at submit time.

## High-Level Decisions

1. **Cart still holds items from many stores. Checkout is per store.** The customer can stage multiple stores and check out one at a time.
2. **New page** `/checkout/[storeId]` collects address + payment method + place order. The cart page becomes a pure list with per-store "Checkout" links.
3. **Payment is mock for MVP, but the flow assumes a future intent/confirm split.** `Payment.status` is always `Pending` after place-order — UPI does not set `Paid`. A future webhook endpoint flips it.
4. **Backend keeps a single endpoint** (`POST /api/v1/orders`) but its contract narrows to one store. The request body gains `store_id` and `payment_method`. The response shape changes from a list to a single Order. This is a breaking change to the existing client; the cart UI is the only caller.

## User Flow

1. Customer browses, adds items from multiple stores → cart at `/cart` shows all of them grouped by store.
2. Customer clicks **Checkout** in a store group's footer → navigates to `/checkout/<storeId>`.
3. Checkout page renders that store's items (read-only), an address picker, a payment-method radio (UPI / Cash, default UPI), and an order summary. "Place Order" is disabled until address and method are chosen.
4. Customer clicks **Place Order** → frontend calls `POST /api/v1/orders` with `{customer_address_id, store_id, payment_method}`.
5. Backend validates the cart for that store, locks inventory, creates Order/OrderItems/Payment(Pending)/Delivery, decrements stock, deletes that store's cart + items, commits.
6. Frontend redirects to `/account/orders?placed=1`. The customer sees the new order. Other stores' carts remain in `/cart`.

## Backend Changes

### Request schema (`backend/app/src/app/schemas/orders.py`)

```python
class PlaceOrderRequest(BaseModel):
    customer_address_id: int = Field(gt=0)
    store_id: int = Field(gt=0)              # NEW — required
    payment_method: PaymentMethod            # NEW — required (Upi | Cash)
```

`PaymentMethod` is the existing enum from `app.models.commerce`.

### Response schema

`POST /api/v1/orders` now returns a single `OrderRead` (status 201), not a list. The existing `PlaceOrderResponse` model in `schemas/orders.py` (currently `{ orders: List[OrderRead] }`) is removed; the route's `response_model` becomes `OrderRead` directly. Frontend client and tests are updated to match.

### Service (`backend/app/src/app/services/checkout.py`)

- Rename `place_orders_from_cart` → `place_order_for_store`. New signature:
  ```python
  async def place_order_for_store(
      session: AsyncSession,
      user: User,
      customer_address_id: int,
      store_id: int,
      payment_method: PaymentMethod,
  ) -> Order: ...
  ```
- Helpers preserved: `_resolve_address`, `_validate_inventory_availability`, `_validate_stores_active`, `_snapshot_product_names`, `_build_order_for_cart`.
- Replace `_load_customer_carts` with `_load_cart_for_store(session, profile_id, store_id) -> tuple[Cart, list[CartItem]]`:
  - 404 `cart_not_found` if no cart row for that (`profile_id`, `store_id`).
  - 400 `cart_empty` if cart exists but has no items.
- `_build_order_for_cart` accepts a `payment_method` argument and constructs `Payment(method=payment_method, status=PaymentStatus.Pending)`. Status is **always `Pending`** — including UPI. This is intentional: a future Razorpay webhook flips it, and MVP staff workflows already mark cash orders paid manually downstream.
- Cart deletion at the end of the service now deletes only the single store's cart + items.

### Route (`backend/app/src/app/api/orders.py`)

- `POST /api/v1/orders` validates the new body and calls `place_order_for_store`.
- Error codes:
  - 422 — missing/invalid `store_id`, `payment_method`, or `customer_address_id`.
  - 404 — `cart_not_found` (no cart for that store) or `invalid_address` (when ambiguous owner check fails).
  - 403 — `invalid_address` (address not owned by caller).
  - 409 — `store_unavailable`, `item_unavailable`, `insufficient_stock` (existing detail shapes preserved).
  - 400 — `cart_empty`.

### Razorpay-ready shape (no code now)

The current response is `OrderRead`. When Razorpay lands, the response will gain an optional `payment_intent: {provider, intent_id} | null` field — the MVP omits it entirely. A future `POST /api/v1/payments/{payment_id}/confirm` endpoint will accept the gateway callback and flip `Payment.status` to `Paid`. None of this is in scope for this spec.

## Frontend Changes

### API client (`frontend/src/lib/orders.ts`)

```ts
export type PaymentMethod = "upi" | "cash";

export async function placeOrder(
  token: string,
  args: {
    customer_address_id: number;
    store_id: number;
    payment_method: PaymentMethod;
  },
): Promise<Order> { ... }
```

Returns a single `Order`. Internal type for the request body is exported for use in the checkout page.

### Cart page (`frontend/src/app/cart/page.tsx`)

- Remove: `addressId` state, `submitting`, `error`, `onCheckout`, the imports `AddressPicker`, `placeOrder`, `useRouter`, and the global address block + grand-total bar.
- Each store group's footer becomes:
  - Subtotal row (existing) on the left.
  - "Checkout" call-to-action on the right, rendered as a `Link` to `/checkout/<store_id>` styled as the primary button.
- Auth/role gating (logged out / non-customer) renders per store group: replace the link with a redirect link to `/login?next=/checkout/<store_id>` or a disabled "Customer login required" state, mirroring the current logic.
- Empty-cart state (`carts.length === 0`) is unchanged.

### New checkout page

Files:
- `frontend/src/app/checkout/[storeId]/page.tsx`
- `frontend/src/app/checkout/[storeId]/page.module.css`

Behavior:
- Client component. Reads `params.storeId` and parses to `Number`.
- On mount: read `carts` and `loading` from `useCart()`. While `loading`, render a skeleton/spinner. After load, find the cart with matching `store_id`. If absent → `router.replace("/cart")`.
- `CartContext` is already auto-refreshed on auth changes and after mutations (see `refreshRemote` in `lib/CartContext.tsx`). To support direct navigation to `/checkout/<id>` without a stale cart, expose a public `refresh: () => Promise<void>` in the context value (delegating to `refreshRemote` for authenticated customers, `refreshLocal` otherwise) and call it once on checkout-page mount. Other consumers may keep the existing implicit behavior.
- Auth guard: if not logged in, redirect to `/login?next=/checkout/<storeId>`. If logged in but role != customer, render the same "Customer login required" message used on the cart page today.
- Local state: `addressId: number | null`, `paymentMethod: PaymentMethod` (default `"upi"`), `submitting: boolean`, `error: string | null`.
- Sections (top to bottom):
  1. Header — store name + "Back to cart" link.
  2. Items review — read-only line items (qty fixed; to change qty user goes back to `/cart`).
  3. Address — `<AddressPicker value={addressId} onChange={setAddressId} />`. If no addresses yet, the picker's "Add one" link points to `/account/settings`.
  4. Payment method — new `PaymentMethodPicker` component (UPI / Cash radio).
  5. Order summary — subtotal, delivery fee, tax (both currently 0), total.
  6. Place Order button — disabled until `addressId !== null` and `paymentMethod` set. On click, calls `placeOrder(token, { customer_address_id: addressId, store_id, payment_method })` and on success `router.push("/account/orders?placed=1")`. On 409 errors, render an inline banner with the reason and a "Back to cart" link.
- CSS module: design tokens consistent with `app/cart/page.module.css`.

### New component (`frontend/src/components/orders/PaymentMethodPicker.tsx`)

Small radio-group component:
```ts
type Props = {
  value: PaymentMethod;
  onChange: (m: PaymentMethod) => void;
};
```
Two options: "UPI" and "Cash on delivery". Two-option layout keeps it trivial to add more later.

### CartContext, Navbar, types

No changes. Cart context still tracks all stores. Navbar cart count still reflects total across stores.

## Data Flow & Concurrency

### Happy path (sequence)

1. Browser → `GET /api/v1/cart` (CartContext refresh on checkout page mount).
2. User submits → `POST /api/v1/orders { customer_address_id, store_id, payment_method }`.
3. Backend transaction:
   - Resolve customer profile (404 if missing).
   - Resolve & authorize address (`_resolve_address`).
   - Load single cart (`_load_cart_for_store`) — 404 / 400 on missing.
   - `lock_inventory_rows(session, inv_ids)` — `FOR UPDATE` row locks.
   - Validate inventory availability + sufficient stock (409).
   - Validate store active (409).
   - Snapshot product names.
   - Build & insert Order, OrderItems, Payment, Delivery; decrement stock on locked rows.
   - Delete cart items, flush, delete cart row.
   - Commit.
4. Browser receives `OrderRead`, navigates to `/account/orders?placed=1`.

### Error matrix

| Server detail | HTTP | UI behavior |
|---|---|---|
| `cart_not_found` | 404 | Toast "Your cart for this store is empty." Redirect `/cart`. |
| `cart_empty` | 400 | Same. |
| `invalid_address` | 403 / 404 | Inline error: "That address is no longer valid. Pick another." Reload addresses. |
| `store_unavailable` | 409 | Banner: "This store is currently closed. Your cart is preserved." Disable submit + back-to-cart link. |
| `item_unavailable` / `insufficient_stock` | 409 | Banner with item names + available stock. Suggest going back to cart. |
| Network / 5xx | — | Generic inline retry. |

### Concurrency

- **Cross-tab same store, double-submit:** the second tab's transaction blocks on `lock_inventory_rows` until the first commits. The first deletes the cart, so the second sees `cart_not_found` (404). Clean — no double charge, no double stock decrement.
- **Cross-tab same store, edit while checkout page is open:** server reloads cart at submit time. Items added in another tab are included; items removed are gone. Acceptable for MVP.
- **Stock dropped between page load and submit:** server validates on submit and returns 409. UI banner directs back to cart.

No live polling. No optimistic locks at the page level.

## Testing

### Backend (`backend/app/tests/test_orders.py` or new `test_checkout.py`)

- `test_place_order_for_store_happy_path_upi` — single-store cart, payment UPI → 201, returned Order has `payment.method == "upi"`, `payment.status == "pending"`. Cart row deleted.
- `test_place_order_for_store_happy_path_cash` — same with Cash.
- `test_place_order_preserves_other_store_carts` — customer has carts at A and B; checkout B → cart A row + items intact, cart B gone.
- `test_place_order_cart_not_found_for_store` — no cart for the requested `store_id` → 404 `cart_not_found`.
- `test_place_order_insufficient_stock` — 409 with item details (existing assertion shape).
- `test_place_order_store_inactive` — 409 `store_unavailable`.
- `test_place_order_invalid_address_not_owned` — 403 `invalid_address`.
- `test_place_order_invalid_address_missing` — 404 `invalid_address`.
- `test_place_order_invalid_payment_method` — 422.
- `test_place_order_missing_store_id` — 422.

Drop / rewrite any existing test asserting multi-store-list response (e.g., `test_place_order_creates_orders_per_store`).

### Frontend

No automated tests in this repo. Manual checklist before merge:
- Two-store cart: clicking Checkout on store A leaves store B intact at `/cart`.
- `/checkout/<id>` direct URL with no matching cart redirects to `/cart`.
- "Add one" address link visible when zero addresses; place button disabled.
- Place UPI order → `/account/orders` shows the new order with method UPI, status pending.
- Place Cash order → method Cash, status pending.
- Stock race: seed inventory `qty=1`, add 1 to cart, manually drop stock to 0 in DB, click Place Order → 409 banner; cart preserved.
- Logged-out user clicking the per-store checkout link is redirected to login with `next=/checkout/<id>`.

### Migration / rollout

- **No DB migration.** Schema unchanged.
- **Breaking change** to `POST /api/v1/orders` request and response. Cart UI is the only caller. Single PR ships backend + frontend + tests together.

## File-Level Change Summary

Backend:
- `backend/app/src/app/schemas/orders.py` — extend `PlaceOrderRequest`; possibly drop `PlaceOrderResponse` wrapper if it returns a list.
- `backend/app/src/app/api/orders.py` — update `POST /orders` route + response model.
- `backend/app/src/app/services/checkout.py` — rename + reshape service to per-store.
- `backend/app/tests/test_orders.py` (or new `test_checkout.py`) — replace multi-store test with the cases above.

Frontend:
- `frontend/src/lib/orders.ts` — new `placeOrder` signature.
- `frontend/src/lib/CartContext.tsx` — expose `refresh: () => Promise<void>` in `CartContextValue` and provider value.
- `frontend/src/app/cart/page.tsx` — drop address/payment/grand-total UI; add per-store checkout link.
- `frontend/src/app/cart/page.module.css` — remove styles for grand-total bar / address block; add "Checkout" CTA styles inside store group.
- `frontend/src/app/checkout/[storeId]/page.tsx` — new page.
- `frontend/src/app/checkout/[storeId]/page.module.css` — new styles.
- `frontend/src/components/orders/PaymentMethodPicker.tsx` — new component.

## Open Questions (resolved)

1. **Cart vs. checkout scope** → Cart holds many stores; checkout is single-store (option A).
2. **UPI integration depth** → Mock for MVP, designed to swap in Razorpay (option B + future-aware).
3. **Address picker location** → On the checkout page, not the cart page (option B).
4. **Endpoint shape** → Modify the existing `POST /api/v1/orders` rather than add a new route (option A).
