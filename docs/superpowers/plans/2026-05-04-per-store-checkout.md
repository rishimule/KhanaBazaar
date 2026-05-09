<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Per-Store Checkout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single multi-store "Place Order" submit with a per-store checkout flow: a new `/checkout/[storeId]` page that collects address + payment method and creates exactly one Order at a time, leaving the customer's other store carts untouched.

**Architecture:** Narrow the existing `POST /api/v1/orders` endpoint to take `{customer_address_id, store_id, payment_method}` and return a single Order. Refactor `place_orders_from_cart` → `place_order_for_store` so it loads the single Cart row matching the requested `store_id`, validates inventory + store + address as today, builds Order/OrderItems/Payment/Delivery, decrements stock, and deletes only that one cart. On the frontend, the cart page becomes a pure list with per-store "Checkout" links; a new `/checkout/[storeId]` page composes the existing `AddressPicker`, a new `PaymentMethodPicker`, and a place-order button. `Payment.status` is always `Pending` so a future Razorpay webhook can flip it without a UI change.

**Tech Stack:** FastAPI / SQLModel / asyncpg (backend), pytest / pytest-asyncio (tests), Next.js 16 App Router / React 19 / TypeScript / CSS Modules (frontend).

**Spec:** `docs/superpowers/specs/2026-05-04-per-store-checkout-design.md`

---

## File Structure

**Backend — modified:**
- `backend/app/src/app/schemas/orders.py` — extend `PlaceOrderRequest`, drop `PlaceOrderResponse`.
- `backend/app/src/app/services/checkout.py` — rename + reshape service to operate on one cart.
- `backend/app/src/app/api/orders.py` — update `POST /orders` route + response model + `dispatch_order_placed` arg.
- `backend/app/tests/test_orders.py` — replace existing place-order tests; add new cases.

**Frontend — created:**
- `frontend/src/app/checkout/[storeId]/page.tsx`
- `frontend/src/app/checkout/[storeId]/page.module.css`
- `frontend/src/components/orders/PaymentMethodPicker.tsx`
- `frontend/src/components/orders/PaymentMethodPicker.module.css`

**Frontend — modified:**
- `frontend/src/types/index.ts` — drop `PlaceOrderResponse` type.
- `frontend/src/lib/orders.ts` — new `placeOrder` signature returning one Order.
- `frontend/src/lib/CartContext.tsx` — expose `refresh` in context value.
- `frontend/src/app/cart/page.tsx` — drop address/grand-total UI; per-store checkout links.
- `frontend/src/app/cart/page.module.css` — drop unused styles, add CTA styles.

---

## Conventions Used Below

- All `pytest` commands run from `backend/app/`.
- All `npm` commands run from `frontend/`.
- "Run X to verify Y" steps include the exact command and the exact pass/fail signal to look for.
- Each commit uses Conventional Commits, no AI co-author trailer (see project memory).

---

## Task 1: Replace existing place-order tests with new contract (failing)

**Files:**
- Modify: `backend/app/tests/test_orders.py:187-264` — `test_place_orders_fans_out_per_store`, `test_place_orders_empty_cart`, `test_place_orders_invalid_address`, `test_place_orders_insufficient_stock`, `_place_orders` helper.

The existing tests assert the old multi-store contract (`{ "orders": [...] }`). Replace them in-place with single-store assertions matching the spec. Downstream tests (cancel, transition, list) call the `_place_orders` helper, so the helper must still return a list of order ids — it now iterates store ids and submits one POST per store.

- [ ] **Step 1: Replace `_place_orders` helper at `test_orders.py:260-264`**

Old block:
```python
async def _place_orders(seed: dict[str, int]) -> list[int]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/orders", json={"customer_address_id": seed["customer_address_id"]})
    assert resp.status_code == 201, resp.text
    return [o["id"] for o in resp.json()["orders"]]
```

New block:
```python
async def _place_orders(seed: dict[str, int]) -> list[int]:
    """Place one order per store in the seeded cart and return their ids in
    the order [store_a, store_b]. Mirrors the per-store contract."""
    order_ids: list[int] = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for store_id in (seed["store_a"], seed["store_b"]):
            resp = await ac.post(
                "/api/v1/orders",
                json={
                    "customer_address_id": seed["customer_address_id"],
                    "store_id": store_id,
                    "payment_method": "upi",
                },
            )
            assert resp.status_code == 201, resp.text
            order_ids.append(resp.json()["id"])
    return order_ids
```

- [ ] **Step 2: Replace `test_place_orders_fans_out_per_store` at `test_orders.py:187-214`**

Rename to `test_place_order_for_store_creates_single_order_upi`. New body:
```python
async def test_place_order_for_store_creates_single_order_upi(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_a"],
                "payment_method": "upi",
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["store_id"] == seed["store_a"]
    assert body["total"] == 100.0
    assert body["payment"]["method"] == "upi"
    assert body["payment"]["status"] == "pending"

    orders = (await session.exec(select(Order))).all()
    assert len(orders) == 1
    payments = (await session.exec(select(Payment))).all()
    assert len(payments) == 1 and payments[0].status == PaymentStatus.Pending
    deliveries = (await session.exec(select(Delivery))).all()
    assert len(deliveries) == 1
    items = (await session.exec(select(OrderItem))).all()
    assert {i.product_name_snapshot for i in items} == {"Apple"}

    inv_a = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_a"]))).first()
    inv_b = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_b"]))).first()
    assert inv_a is not None and inv_b is not None
    assert inv_a.stock == 8  # 10 − 2
    assert inv_b.stock == 4  # untouched

    # Only store_a's cart was deleted; store_b's cart + item remain.
    remaining_carts = (await session.exec(select(Cart))).all()
    assert len(remaining_carts) == 1
    assert remaining_carts[0].store_id == seed["store_b"]
    remaining_items = (await session.exec(select(CartItem))).all()
    assert len(remaining_items) == 1
```

- [ ] **Step 3: Replace `test_place_orders_empty_cart` at `test_orders.py:217-223`**

Rename to `test_place_order_cart_not_found_for_store`. New body:
```python
async def test_place_order_cart_not_found_for_store(
    as_other_customer: Any, seed: dict[str, int]
) -> None:
    # other_customer has a CustomerProfile but no cart for store_a. The address
    # belongs to the main customer, so the address-ownership check fires first.
    # We use a separate test (below) for the pure cart_not_found case.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_a"],
                "payment_method": "cash",
            },
        )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "invalid_address"
```

- [ ] **Step 4: Replace `test_place_orders_invalid_address` at `test_orders.py:226-229`**

Rename to `test_place_order_invalid_address_missing`. New body:
```python
async def test_place_order_invalid_address_missing(
    as_customer: Any, seed: dict[str, int]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": 9999,
                "store_id": seed["store_a"],
                "payment_method": "upi",
            },
        )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "invalid_address"
```

- [ ] **Step 5: Replace `test_place_orders_insufficient_stock` at `test_orders.py:232-257`**

Rename to `test_place_order_insufficient_stock`. New body:
```python
async def test_place_order_insufficient_stock(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    inv = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_a"]))).first()
    assert inv is not None
    inv.stock = 1  # cart wants 2
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_a"],
                "payment_method": "upi",
            },
        )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["detail"] == "insufficient_stock"

    inv = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_a"]))).first()
    inv_b = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_b"]))).first()
    assert inv is not None and inv_b is not None
    assert inv.stock == 1 and inv_b.stock == 4

    assert (await session.exec(select(Order))).all() == []
    assert (await session.exec(select(Payment))).all() == []
    assert (await session.exec(select(Delivery))).all() == []
    assert (await session.exec(select(OrderItem))).all() == []
    remaining_carts = (await session.exec(select(Cart))).all()
    assert len(remaining_carts) == 2  # cart_a + cart_b still present
    remaining_items = (await session.exec(select(CartItem))).all()
    assert len(remaining_items) == 2
```

- [ ] **Step 6: Run the modified tests to confirm they fail against the un-modified server**

Run:
```bash
uv run pytest tests/test_orders.py::test_place_order_for_store_creates_single_order_upi tests/test_orders.py::test_place_order_cart_not_found_for_store tests/test_orders.py::test_place_order_invalid_address_missing tests/test_orders.py::test_place_order_insufficient_stock -v
```
Expected: all four fail (most likely 422 because the server still rejects the new body fields, or the response shape mismatches `body["store_id"]`).

- [ ] **Step 7: Commit the failing tests**

```bash
git add backend/app/tests/test_orders.py
git commit -m "test(orders): assert per-store checkout contract"
```

---

## Task 2: Add new tests for cart_not_found, cash, payment-method validation, and other-store-cart preservation

**Files:**
- Modify: `backend/app/tests/test_orders.py` — append new tests after `test_place_order_insufficient_stock`.

These tests add coverage that does not exist today. They will also fail until Tasks 3-5 implement the new contract.

- [ ] **Step 1: Append `test_place_order_for_store_cash_method` to `test_orders.py`**

```python
async def test_place_order_for_store_cash_method(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_b"],
                "payment_method": "cash",
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["payment"]["method"] == "cash"
    assert body["payment"]["status"] == "pending"
    assert body["store_id"] == seed["store_b"]
```

- [ ] **Step 2: Append `test_place_order_pure_cart_not_found` to `test_orders.py`**

This covers the case where the customer owns a valid address but has no cart for the requested store. Use the main customer (who has carts for store_a and store_b) and submit for a non-existent third store id.

```python
async def test_place_order_pure_cart_not_found(
    as_customer: Any, seed: dict[str, int]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": 999_999,  # no cart, no store
                "payment_method": "upi",
            },
        )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "cart_not_found"
```

- [ ] **Step 3: Append `test_place_order_invalid_payment_method` to `test_orders.py`**

```python
async def test_place_order_invalid_payment_method(
    as_customer: Any, seed: dict[str, int]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_a"],
                "payment_method": "bitcoin",
            },
        )
    assert resp.status_code == 422
```

- [ ] **Step 4: Append `test_place_order_missing_store_id` to `test_orders.py`**

```python
async def test_place_order_missing_store_id(
    as_customer: Any, seed: dict[str, int]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "payment_method": "upi",
            },
        )
    assert resp.status_code == 422
```

- [ ] **Step 5: Append `test_place_order_store_inactive` to `test_orders.py`**

Add `Store` to the existing `from app.models.store import …` import line at the top of the file (already imports `StoreInventory`; just append `Store`).

```python
async def test_place_order_store_inactive(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    store = (await session.exec(select(Store).where(Store.id == seed["store_a"]))).first()
    assert store is not None
    store.is_active = False
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_a"],
                "payment_method": "upi",
            },
        )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["detail"] == "store_unavailable"
    assert detail["store_id"] == seed["store_a"]
```

If `Store` is not yet imported at the top of the file, also do this edit:
```python
# in the existing imports, change:
from app.models.store import Store, StoreInventory
```
(Look for `from app.models.store import StoreInventory` — replace with the line above. If the line already imports `Store`, no change.)

- [ ] **Step 6: Run new tests to confirm they fail**

Run:
```bash
uv run pytest tests/test_orders.py -k "test_place_order" -v
```
Expected: all six new test functions plus the four from Task 1 fail (10 failures total). Existing non-place_order tests should still pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/tests/test_orders.py
git commit -m "test(orders): cover cash, cart_not_found, payment validation, store_unavailable"
```

---

## Task 3: Update request/response schemas

**Files:**
- Modify: `backend/app/src/app/schemas/orders.py:58-63` — extend `PlaceOrderRequest`, remove `PlaceOrderResponse`.

- [ ] **Step 1: Edit `PlaceOrderRequest` and remove `PlaceOrderResponse`**

Old block (lines 58-63):
```python
class PlaceOrderRequest(BaseModel):
    customer_address_id: int = Field(gt=0)


class PlaceOrderResponse(BaseModel):
    orders: List[OrderRead]
```

New block:
```python
class PlaceOrderRequest(BaseModel):
    customer_address_id: int = Field(gt=0)
    store_id: int = Field(gt=0)
    payment_method: PaymentMethod
```

- [ ] **Step 2: Add `PaymentMethod` to imports at the top of `schemas/orders.py`**

Find the existing import line for `app.models.commerce` (it imports e.g. `OrderStatus`, `PaymentStatus`, `DeliveryStatus`). Add `PaymentMethod` to that same line. If no such import exists yet, add:
```python
from app.models.commerce import PaymentMethod
```
near the other model imports.

- [ ] **Step 3: Verify the file compiles**

Run:
```bash
uv run python -c "from app.schemas.orders import PlaceOrderRequest; print(PlaceOrderRequest.model_fields.keys())"
```
Expected output (order may vary):
```
dict_keys(['customer_address_id', 'store_id', 'payment_method'])
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/schemas/orders.py
git commit -m "feat(orders): widen PlaceOrderRequest to per-store + payment_method"
```

---

## Task 4: Refactor checkout service to per-store

**Files:**
- Modify: `backend/app/src/app/services/checkout.py` — rename `place_orders_from_cart`, replace `_load_customer_carts` with `_load_cart_for_store`, thread `payment_method` through `_build_order_for_cart`.

- [ ] **Step 1: Replace `_load_customer_carts` with `_load_cart_for_store`**

Find the existing `_load_customer_carts` function (around line 143-160). Replace it entirely with:

```python
async def _load_cart_for_store(
    session: AsyncSession, customer_profile_id: int, store_id: int
) -> tuple[Cart, list[CartItem]]:
    """Return (cart, items) for the customer's cart at this store. Raises
    404 cart_not_found if the customer has no cart row for store_id; 400
    cart_empty if the cart exists but has zero items."""
    cart_result = await session.exec(
        select(Cart).where(
            Cart.customer_profile_id == customer_profile_id,
            Cart.store_id == store_id,
        )
    )
    cart = cart_result.first()
    if cart is None:
        raise HTTPException(status_code=404, detail="cart_not_found")
    assert cart.id is not None
    items_result = await session.exec(
        select(CartItem).where(CartItem.cart_id == cart.id)
    )
    cart_items = list(items_result.all())
    if not cart_items:
        raise HTTPException(status_code=400, detail="cart_empty")
    return cart, cart_items
```

- [ ] **Step 2: Update `_build_order_for_cart` to accept `payment_method`**

Find the function (around line 82-119). Change its signature and the `Payment(...)` call:

Old signature:
```python
def _build_order_for_cart(
    *, profile_id: int, address_id: int, address_snapshot: str,
    cart: Cart, items: list[CartItem],
    inv_by_id: dict[int, StoreInventory], name_by_inv: dict[int, str],
) -> tuple[Order, list[OrderItem], Payment, Delivery]:
```

New signature:
```python
def _build_order_for_cart(
    *, profile_id: int, address_id: int, address_snapshot: str,
    cart: Cart, items: list[CartItem],
    inv_by_id: dict[int, StoreInventory], name_by_inv: dict[int, str],
    payment_method: PaymentMethod,
) -> tuple[Order, list[OrderItem], Payment, Delivery]:
```

Inside the function, change:
```python
payment = Payment(
    amount=total, method=PaymentMethod.Cash, status=PaymentStatus.Pending,
)
```
to:
```python
payment = Payment(
    amount=total, method=payment_method, status=PaymentStatus.Pending,
)
```

- [ ] **Step 3: Replace `place_orders_from_cart` with `place_order_for_store`**

Find the function at the bottom of the file (around line 188-254). Replace entirely with:

```python
async def place_order_for_store(
    session: AsyncSession,
    user: User,
    customer_address_id: int,
    store_id: int,
    payment_method: PaymentMethod,
) -> Order:
    profile = await _customer_profile(session, user)
    assert profile.id is not None

    address_id, address_snapshot = await _resolve_address(
        session, customer_address_id, profile.id
    )

    cart, cart_items = await _load_cart_for_store(session, profile.id, store_id)

    inv_ids = [item.inventory_id for item in cart_items]
    locked_inv = await lock_inventory_rows(session, inv_ids)
    inv_by_id: dict[int, StoreInventory] = {
        inv.id: inv for inv in locked_inv if inv.id is not None
    }

    _validate_inventory_availability(cart_items, inv_by_id)
    await _validate_stores_active(session, [store_id])

    name_by_inv = await _snapshot_product_names(session, inv_ids)

    order, order_items, payment, delivery = _build_order_for_cart(
        profile_id=profile.id, address_id=address_id,
        address_snapshot=address_snapshot, cart=cart, items=cart_items,
        inv_by_id=inv_by_id, name_by_inv=name_by_inv,
        payment_method=payment_method,
    )
    session.add(order)
    await session.flush()
    assert order.id is not None
    for oi in order_items:
        oi.order_id = order.id
        session.add(oi)
        assert oi.inventory_id is not None
        decrement_stock(inv_by_id[oi.inventory_id], oi.quantity)
    payment.order_id = order.id
    delivery.order_id = order.id
    session.add(payment)
    session.add(delivery)

    # Clear only this store's cart (items first to satisfy FK).
    for item in cart_items:
        await session.delete(item)
    await session.flush()
    await session.delete(cart)

    await session.commit()
    await session.refresh(order)
    return order
```

- [ ] **Step 4: Verify the file compiles**

Run:
```bash
uv run python -c "from app.services.checkout import place_order_for_store; print(place_order_for_store.__doc__ or 'ok')"
```
Expected: prints `ok` (no traceback).

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/services/checkout.py
git commit -m "refactor(checkout): place_order_for_store with payment_method"
```

---

## Task 5: Update the route to use the new service and response

**Files:**
- Modify: `backend/app/src/app/api/orders.py:24-34` (imports), `:215-227` (route).

- [ ] **Step 1: Update imports**

Find the import block at lines 24-34. Change `place_orders_from_cart` → `place_order_for_store` and drop `PlaceOrderResponse` from `app.schemas.orders`:

Old:
```python
from app.schemas.orders import (
    DeliveryRead,
    OrderItemRead,
    OrderListResponse,
    OrderRead,
    PaymentRead,
    PlaceOrderRequest,
    PlaceOrderResponse,
    TransitionRequest,
)
from app.services.checkout import place_orders_from_cart
```

New:
```python
from app.schemas.orders import (
    DeliveryRead,
    OrderItemRead,
    OrderListResponse,
    OrderRead,
    PaymentRead,
    PlaceOrderRequest,
    TransitionRequest,
)
from app.services.checkout import place_order_for_store
```

- [ ] **Step 2: Update the route at `orders.py:215-227`**

Old block:
```python
@router.post("", response_model=PlaceOrderResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=PlaceOrderResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def place_order(
    payload: PlaceOrderRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> PlaceOrderResponse:
    orders = await place_orders_from_cart(session, user, payload.customer_address_id)
    order_ids = [o.id for o in orders if o.id is not None]
    dispatch_order_placed(order_ids)
    return PlaceOrderResponse(
        orders=[await _serialize_order(session, o, include_customer_name=False) for o in orders]
    )
```

New block:
```python
@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=OrderRead, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def place_order(
    payload: PlaceOrderRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> OrderRead:
    order = await place_order_for_store(
        session,
        user,
        payload.customer_address_id,
        payload.store_id,
        payload.payment_method,
    )
    if order.id is not None:
        dispatch_order_placed([order.id])
    return await _serialize_order(session, order, include_customer_name=False)
```

- [ ] **Step 3: Run the order-test subset**

Run:
```bash
uv run pytest tests/test_orders.py -k "place_order" -v
```
Expected: the 10 place-order tests added in Tasks 1-2 pass. If any fail, fix in this task before moving on.

- [ ] **Step 4: Run the full backend test suite**

Run:
```bash
uv run pytest -v
```
Expected: all tests pass. Pay attention to `test_orders.py` cancel/transition/list tests that depend on the `_place_orders` helper — they should now exercise two POSTs internally and still pass.

- [ ] **Step 5: Run lint and types**

```bash
uv run ruff check .
uv run mypy .
```
Expected: clean. Fix any issues before committing.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/api/orders.py
git commit -m "feat(orders): per-store place_order route returns single Order"
```

---

## Task 6: Update frontend types

**Files:**
- Modify: `frontend/src/types/index.ts:215-217` — drop `PlaceOrderResponse`.

- [ ] **Step 1: Delete `PlaceOrderResponse`**

Remove this block (lines 215-217):
```ts
export interface PlaceOrderResponse {
  orders: Order[];
}
```

- [ ] **Step 2: Confirm `PaymentMethod` is already exported**

Check `frontend/src/types/index.ts` for the line `export type PaymentMethod = "cash" | "upi";` (it exists at line 173). No edit needed.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "types(orders): drop PlaceOrderResponse wrapper"
```

---

## Task 7: Update `placeOrder` API client

**Files:**
- Modify: `frontend/src/lib/orders.ts:17-27` (signature), `:1-2` (imports).

- [ ] **Step 1: Update imports**

Old line 1-2:
```ts
import { get, post } from "@/lib/api";
import type { Order, OrderListResponse, PlaceOrderResponse } from "@/types";
```
New:
```ts
import { get, post } from "@/lib/api";
import type { Order, OrderListResponse, PaymentMethod } from "@/types";
```

- [ ] **Step 2: Replace `placeOrder`**

Old block (lines 17-27):
```ts
export async function placeOrder(
  token: string,
  customerAddressId: number
): Promise<Order[]> {
  const data = await post<PlaceOrderResponse>(
    "/api/v1/orders",
    { customer_address_id: customerAddressId },
    token
  );
  return data.orders;
}
```

New block:
```ts
export interface PlaceOrderArgs {
  customerAddressId: number;
  storeId: number;
  paymentMethod: PaymentMethod;
}

export async function placeOrder(
  token: string,
  args: PlaceOrderArgs
): Promise<Order> {
  return post<Order>(
    "/api/v1/orders",
    {
      customer_address_id: args.customerAddressId,
      store_id: args.storeId,
      payment_method: args.paymentMethod,
    },
    token
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run:
```bash
npm run lint
```
Expected: errors point at `frontend/src/app/cart/page.tsx` (still calling `placeOrder` with old signature). Those are fixed in Task 11.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/orders.ts
git commit -m "feat(orders-client): placeOrder takes storeId and paymentMethod"
```

---

## Task 8: Expose `refresh` from CartContext

**Files:**
- Modify: `frontend/src/lib/CartContext.tsx:19-29` (interface), `:228-238` (provider value).

- [ ] **Step 1: Add `refresh` to the context interface**

Old (lines 19-29):
```ts
interface CartContextValue {
  carts: Cart[];
  cartCount: number;
  loading: boolean;
  addItem: (storeId: number, storeName: string, item: CartItem) => Promise<void>;
  removeItem: (storeId: number, productId: number) => Promise<void>;
  updateQty: (storeId: number, productId: number, qty: number) => Promise<void>;
  clearStoreCart: (storeId: number) => Promise<void>;
  getTotal: (cart: Cart) => number;
  grandTotal: number;
}
```
New: append `refresh` to the same interface:
```ts
interface CartContextValue {
  carts: Cart[];
  cartCount: number;
  loading: boolean;
  addItem: (storeId: number, storeName: string, item: CartItem) => Promise<void>;
  removeItem: (storeId: number, productId: number) => Promise<void>;
  updateQty: (storeId: number, productId: number, qty: number) => Promise<void>;
  clearStoreCart: (storeId: number) => Promise<void>;
  getTotal: (cart: Cart) => number;
  grandTotal: number;
  refresh: () => Promise<void>;
}
```

- [ ] **Step 2: Define `refresh` and add it to the provider value**

Inside `CartProvider`, after the existing `refreshLocal` and `refreshRemote` callbacks (around line 61), add:
```ts
const refresh = useCallback(async () => {
  if (isCustomer) {
    await refreshRemote();
  } else {
    refreshLocal();
  }
}, [isCustomer, refreshRemote, refreshLocal]);
```
**Important:** `isCustomer` is declared at line 105 (after the `useEffect`). Move the `const isCustomer = …` line up to just after `refreshRemote` (before defining `refresh`). The remaining code that reads `isCustomer` continues to work because it's all later in the file.

Then in the `value` object (around lines 228-238), append `refresh`:
```ts
const value: CartContextValue = {
  carts,
  cartCount,
  loading,
  addItem,
  removeItem,
  updateQty,
  clearStoreCart,
  getTotal: getCartTotal,
  grandTotal,
  refresh,
};
```

- [ ] **Step 3: Verify lint passes**

```bash
npm run lint
```
Expected: same `cart/page.tsx` errors as before, but no new errors in CartContext.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/CartContext.tsx
git commit -m "feat(cart-context): expose refresh() for direct callers"
```

---

## Task 9: Build the `PaymentMethodPicker` component

**Files:**
- Create: `frontend/src/components/orders/PaymentMethodPicker.tsx`
- Create: `frontend/src/components/orders/PaymentMethodPicker.module.css`

- [ ] **Step 1: Create `PaymentMethodPicker.tsx`**

```tsx
"use client";

import type { PaymentMethod } from "@/types";
import styles from "./PaymentMethodPicker.module.css";

interface Props {
  value: PaymentMethod;
  onChange: (method: PaymentMethod) => void;
}

const OPTIONS: { value: PaymentMethod; label: string; hint: string }[] = [
  { value: "upi", label: "UPI", hint: "Pay via UPI app" },
  { value: "cash", label: "Cash on delivery", hint: "Pay when you receive" },
];

export default function PaymentMethodPicker({ value, onChange }: Props) {
  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.legend}>Payment method</legend>
      <div className={styles.options}>
        {OPTIONS.map((opt) => (
          <label
            key={opt.value}
            className={`${styles.option} ${value === opt.value ? styles.selected : ""}`}
          >
            <input
              type="radio"
              name="payment_method"
              value={opt.value}
              checked={value === opt.value}
              onChange={() => onChange(opt.value)}
              className={styles.radio}
            />
            <span className={styles.label}>{opt.label}</span>
            <span className={styles.hint}>{opt.hint}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
```

- [ ] **Step 2: Create `PaymentMethodPicker.module.css`**

```css
.fieldset {
  border: none;
  padding: 0;
  margin: 0;
}

.legend {
  font-size: var(--font-base);
  font-weight: var(--weight-semibold);
  color: var(--color-neutral-900);
  margin-bottom: var(--space-3);
}

.options {
  display: grid;
  gap: var(--space-3);
}

.option {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color var(--duration-fast) var(--ease-out),
    background-color var(--duration-fast) var(--ease-out);
}

.option:hover {
  border-color: var(--color-primary-400);
}

.selected {
  border-color: var(--color-primary-500);
  background-color: var(--color-primary-50);
}

.radio {
  accent-color: var(--color-primary-500);
}

.label {
  font-weight: var(--weight-semibold);
  color: var(--color-neutral-900);
}

.hint {
  font-size: var(--font-sm);
  color: var(--color-neutral-500);
}
```

- [ ] **Step 3: Verify lint passes**

```bash
npm run lint
```
Expected: no new errors in the new files (the cart-page error remains until Task 11).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/orders/PaymentMethodPicker.tsx frontend/src/components/orders/PaymentMethodPicker.module.css
git commit -m "feat(orders): PaymentMethodPicker component"
```

---

## Task 10: Build the new `/checkout/[storeId]` page

**Files:**
- Create: `frontend/src/app/checkout/[storeId]/page.tsx`
- Create: `frontend/src/app/checkout/[storeId]/page.module.css`

- [ ] **Step 1: Create `page.tsx`**

```tsx
"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { placeOrder } from "@/lib/orders";
import AddressPicker from "@/components/orders/AddressPicker";
import PaymentMethodPicker from "@/components/orders/PaymentMethodPicker";
import type { PaymentMethod } from "@/types";
import styles from "./page.module.css";

export default function CheckoutPage() {
  const params = useParams<{ storeId: string }>();
  const storeId = Number(params.storeId);
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();
  const { carts, loading: cartLoading, refresh, getTotal } = useCart();

  const [addressId, setAddressId] = useState<number | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("upi");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pull a fresh copy on mount (handles direct navigation to this URL).
  useEffect(() => {
    refresh();
    // refresh has stable identity (useCallback in CartContext); intentionally
    // depending only on storeId so we re-fetch when navigating between stores.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId]);

  const cart = useMemo(
    () => carts.find((c) => c.store_id === storeId),
    [carts, storeId]
  );

  const isCustomer = dbUser?.role === "customer";

  // Redirect to /cart if no matching cart after the cart context finished loading.
  useEffect(() => {
    if (!authLoading && !cartLoading && isCustomer && !cart) {
      router.replace("/cart");
    }
  }, [authLoading, cartLoading, isCustomer, cart, router]);

  if (authLoading || cartLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <p className={styles.loadingText}>Loading…</p>
        </div>
      </div>
    );
  }

  if (!dbUser) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <p className={styles.loadingText}>
            <Link href={`/login?next=/checkout/${storeId}`}>Log in</Link> to check out.
          </p>
        </div>
      </div>
    );
  }

  if (!isCustomer) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <p className={styles.loadingText}>Customer login required.</p>
        </div>
      </div>
    );
  }

  if (!cart) {
    // The redirect effect will fire; render nothing while it does.
    return null;
  }

  const subtotal = getTotal(cart);
  const deliveryFee = 0;
  const tax = 0;
  const total = subtotal + deliveryFee + tax;

  const onPlaceOrder = async () => {
    if (!token || addressId === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await placeOrder(token, {
        customerAddressId: addressId,
        storeId,
        paymentMethod,
      });
      router.push("/account/orders?placed=1");
    } catch (e) {
      const detail = (e as { detail?: unknown })?.detail;
      if (typeof detail === "string") {
        setError(detail);
      } else if (detail && typeof detail === "object" && "detail" in detail) {
        setError(String((detail as { detail: unknown }).detail));
      } else {
        setError("Could not place order. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        <div className={styles.header}>
          <Link href="/cart" className={styles.backLink}>
            ← Back to cart
          </Link>
          <h1 className={styles.title}>Checkout — {cart.store_name}</h1>
        </div>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Items</h2>
          <ul className={styles.itemList}>
            {cart.items.map((item) => (
              <li key={item.product_id} className={styles.itemRow}>
                <span className={styles.itemName}>{item.product_name}</span>
                <span className={styles.itemQty}>× {item.quantity}</span>
                <span className={styles.itemPrice}>₹{item.price * item.quantity}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Delivery address</h2>
          <AddressPicker value={addressId} onChange={setAddressId} />
        </section>

        <section className={styles.section}>
          <PaymentMethodPicker value={paymentMethod} onChange={setPaymentMethod} />
        </section>

        <section className={styles.summary}>
          <div className={styles.summaryRow}>
            <span>Subtotal</span>
            <span>₹{subtotal}</span>
          </div>
          <div className={styles.summaryRow}>
            <span>Delivery fee</span>
            <span>₹{deliveryFee}</span>
          </div>
          <div className={styles.summaryRow}>
            <span>Tax</span>
            <span>₹{tax}</span>
          </div>
          <div className={`${styles.summaryRow} ${styles.summaryTotal}`}>
            <span>Total</span>
            <span>₹{total}</span>
          </div>
        </section>

        {error && <div className={styles.error}>{error}</div>}

        <button
          className={styles.placeBtn}
          onClick={onPlaceOrder}
          disabled={submitting || addressId === null}
        >
          {submitting ? "Placing order…" : `Place Order — ₹${total}`}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `page.module.css`**

```css
.page {
  min-height: 60vh;
  padding: var(--space-8) var(--space-4) var(--space-12);
}

.pageInner {
  max-width: var(--container-md);
  margin-inline: auto;
  display: grid;
  gap: var(--space-6);
}

.header {
  display: grid;
  gap: var(--space-2);
}

.backLink {
  font-size: var(--font-sm);
  color: var(--color-primary-600);
  text-decoration: none;
}

.backLink:hover {
  text-decoration: underline;
}

.title {
  font-size: var(--font-2xl);
  font-weight: var(--weight-bold);
  color: var(--color-neutral-900);
  margin: 0;
}

.section {
  background: white;
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}

.sectionTitle {
  font-size: var(--font-base);
  font-weight: var(--weight-semibold);
  color: var(--color-neutral-900);
  margin: 0 0 var(--space-3);
}

.itemList {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: var(--space-2);
}

.itemRow {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: var(--space-3);
  align-items: baseline;
  font-size: var(--font-sm);
}

.itemName {
  color: var(--color-neutral-900);
  font-weight: var(--weight-medium);
}

.itemQty {
  color: var(--color-neutral-500);
}

.itemPrice {
  color: var(--color-neutral-900);
  font-weight: var(--weight-semibold);
}

.summary {
  background: var(--color-neutral-50);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  display: grid;
  gap: var(--space-2);
}

.summaryRow {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-sm);
  color: var(--color-neutral-700);
}

.summaryTotal {
  font-size: var(--font-lg);
  font-weight: var(--weight-bold);
  color: var(--color-neutral-900);
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-neutral-200);
  margin-top: var(--space-2);
}

.error {
  background: hsla(0, 84%, 60%, 0.08);
  border: 1px solid hsla(0, 84%, 60%, 0.3);
  color: var(--color-error);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  font-size: var(--font-sm);
}

.placeBtn {
  background: var(--gradient-primary);
  color: white;
  font-size: var(--font-base);
  font-weight: var(--weight-semibold);
  padding: var(--space-4) var(--space-6);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: opacity var(--duration-fast) var(--ease-out);
}

.placeBtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.placeBtn:not(:disabled):hover {
  opacity: 0.9;
}

.loadingText {
  text-align: center;
  color: var(--color-neutral-500);
  font-size: var(--font-base);
}
```

- [ ] **Step 3: Verify lint**

```bash
npm run lint
```
Expected: cart-page errors remain (fixed in Task 11), no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/checkout/
git commit -m "feat(checkout): per-store checkout page"
```

---

## Task 11: Strip the cart page of address + grand-total UI; add per-store checkout links

**Files:**
- Modify: `frontend/src/app/cart/page.tsx` — entire body simplified.

- [ ] **Step 1: Replace the entire file**

Overwrite `frontend/src/app/cart/page.tsx` with:

```tsx
"use client";

import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import styles from "./page.module.css";

export default function CartPage() {
  const { carts, removeItem, updateQty, clearStoreCart, getTotal } = useCart();
  const { dbUser } = useAuth();

  if (carts.length === 0) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>🛒</div>
            <h1 className={styles.emptyTitle}>Your cart is empty</h1>
            <p className={styles.emptyText}>
              Looks like you haven&apos;t added anything yet. Browse nearby
              stores and start adding items!
            </p>
            <Link href="/stores" className="btn btn-primary" id="empty-cart-shop">
              Start Shopping
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const isCustomer = dbUser?.role === "customer";

  const renderCheckoutCta = (storeId: number, subtotal: number) => {
    if (!dbUser) {
      return (
        <Link href={`/login?next=/checkout/${storeId}`} className={styles.checkoutBtn}>
          Login to checkout
        </Link>
      );
    }
    if (!isCustomer) {
      return (
        <span className={styles.checkoutBtn} aria-disabled>
          Customer login required
        </span>
      );
    }
    return (
      <Link href={`/checkout/${storeId}`} className={styles.checkoutBtn}>
        Checkout · ₹{subtotal}
      </Link>
    );
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        <div className={styles.header}>
          <h1 className={styles.title}>
            Your <span className={styles.titleAccent}>Cart</span>
          </h1>
          <p className={styles.subtitle}>
            {carts.length} store{carts.length > 1 ? "s" : ""} ·{" "}
            {carts.reduce(
              (sum, c) => sum + c.items.reduce((s, i) => s + i.quantity, 0),
              0
            )}{" "}
            items
          </p>
        </div>

        {carts.map((cart) => {
          const subtotal = getTotal(cart);
          return (
            <div key={cart.store_id} className={styles.storeGroup}>
              <div className={styles.storeGroupHeader}>
                <div className={styles.storeGroupTitle}>
                  🏪{" "}
                  <Link
                    href={`/stores/${cart.store_id}`}
                    className={styles.storeGroupLink}
                  >
                    {cart.store_name}
                  </Link>
                </div>
                <button
                  className={styles.clearBtn}
                  onClick={() => clearStoreCart(cart.store_id)}
                >
                  Clear all
                </button>
              </div>

              {cart.items.map((item) => (
                <div key={item.product_id} className={styles.cartItem}>
                  <div className={styles.itemEmoji}>📦</div>

                  <div className={styles.itemInfo}>
                    <div className={styles.itemName}>{item.product_name}</div>
                    <div className={styles.itemPrice}>₹{item.price} each</div>
                  </div>

                  <div className={styles.qtyControls}>
                    <button
                      className={styles.qtyBtn}
                      onClick={() =>
                        item.quantity <= 1
                          ? removeItem(cart.store_id, item.product_id)
                          : updateQty(
                              cart.store_id,
                              item.product_id,
                              item.quantity - 1
                            )
                      }
                    >
                      −
                    </button>
                    <span className={styles.qtyValue}>{item.quantity}</span>
                    <button
                      className={styles.qtyBtn}
                      onClick={() =>
                        updateQty(
                          cart.store_id,
                          item.product_id,
                          item.quantity + 1
                        )
                      }
                    >
                      +
                    </button>
                  </div>

                  <div className={styles.itemTotal}>
                    ₹{item.price * item.quantity}
                  </div>

                  <button
                    className={styles.removeBtn}
                    onClick={() => removeItem(cart.store_id, item.product_id)}
                    aria-label={`Remove ${item.product_name}`}
                  >
                    ✕
                  </button>
                </div>
              ))}

              <div className={styles.storeFooter}>
                <span className={styles.storeSubtotalValue}>
                  Subtotal: ₹{subtotal}
                </span>
                {renderCheckoutCta(cart.store_id, subtotal)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update `cart/page.module.css` to add `.storeFooter` and reuse `.checkoutBtn`**

In `frontend/src/app/cart/page.module.css`, find the existing `.storeSubtotal` rule and rename it to `.storeFooter`, changing the layout to put the CTA on the right. Find this block:
```css
.storeSubtotal {
  /* existing styles */
}
```
and replace it with:
```css
.storeFooter {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4);
  border-top: 1px solid var(--color-neutral-200);
  background: var(--color-neutral-50);
  border-bottom-left-radius: var(--radius-lg);
  border-bottom-right-radius: var(--radius-lg);
  gap: var(--space-3);
}
```

The existing `.storeSubtotalValue` rule can stay; it now only styles the text on the left of the footer.

The existing `.checkoutBtn`, `.totalBar`, `.totalLabel`, `.totalRight`, `.totalValue`, `.addressBlock`, and `.error` rules can be removed in this file *only if* they are unused elsewhere. The new cart page reuses `.checkoutBtn` for the per-store CTA, so keep `.checkoutBtn`. Remove `.totalBar`, `.totalLabel`, `.totalRight`, `.totalValue`, `.addressBlock`, and `.error` (no longer referenced from `cart/page.tsx`).

- [ ] **Step 3: Verify lint and types**

```bash
npm run lint
```
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/cart/page.tsx frontend/src/app/cart/page.module.css
git commit -m "feat(cart): per-store checkout links; drop global address+total"
```

---

## Task 12: End-to-end manual smoke test

This task verifies the full flow against a running dev stack. No code changes.

- [ ] **Step 1: Start the backend**

In `backend/app/`:
```bash
docker-compose up -d
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```
Expected: server listens on `:8000`.

- [ ] **Step 2: Start the frontend**

In `frontend/`:
```bash
npm run dev
```
Expected: dev server on `:3000`.

- [ ] **Step 3: Seed two store carts**

In a browser:
1. Log in as a customer (use any seeded customer email; OTP shows in backend console with `EMAIL_PROVIDER=console`).
2. Navigate to `/stores`. Pick one store, add an item to cart. Pick a second store, add a different item.
3. Open `/cart`. Verify two store groups appear, each with its own "Checkout · ₹X" button. Verify there is no global grand-total bar and no address picker on this page.

- [ ] **Step 4: Per-store happy path (UPI)**

1. Click "Checkout" on store A. URL becomes `/checkout/<storeA-id>`.
2. Verify the page shows: store name in the header, the items from store A only, the address picker, the payment-method picker (UPI selected by default), and an order summary.
3. Pick an address (or follow "Add one" to `/account/settings`, add an address, return).
4. Leave UPI selected. Click "Place Order".
5. Verify redirect to `/account/orders?placed=1`. The new order shows up with method `upi`, status `pending`.
6. Navigate back to `/cart`. Verify only store B's cart remains.

- [ ] **Step 5: Per-store happy path (Cash)**

1. Click "Checkout" on store B.
2. Switch payment method to "Cash on delivery". Click "Place Order".
3. Verify the new order on `/account/orders` shows method `cash`, status `pending`.
4. `/cart` is now empty.

- [ ] **Step 6: Direct-URL safety**

Visit `/checkout/999999` directly. Expected: redirect to `/cart`.

- [ ] **Step 7: Logged-out CTA**

Log out. Visit `/cart` (it shows whatever is in localStorage, possibly empty). If it has items, the per-store CTAs should read "Login to checkout" and link to `/login?next=/checkout/<id>`. If empty, the empty-state UI is shown.

- [ ] **Step 8: Stock-race**

Re-seed a single-item cart for one store. In another terminal, run a SQL update to drop the inventory row's `stock` to 0 (or use the seller UI). Click "Place Order" on the checkout page. Expected: an inline error appears reading something like `insufficient_stock` (or the friendlier message), and the cart row remains intact at `/cart`.

- [ ] **Step 9: No commit (manual verification only)**

This task does not commit. If issues are found, return to the relevant task above and add a fix step there.

---

## Task 13: Final sanity check + push

- [ ] **Step 1: Run all backend checks**

```bash
cd backend/app
uv run pytest -v
uv run ruff check .
uv run mypy .
```
Expected: all green.

- [ ] **Step 2: Run all frontend checks**

```bash
cd frontend
npm run lint
npm run build
```
Expected: build completes without TypeScript errors.

- [ ] **Step 3: Push the branch**

```bash
git push -u origin feat/per-store-checkout
```

- [ ] **Step 4: Open a PR (only if user has explicitly approved)**

Per `CLAUDE.md`, do not open the PR without explicit user permission. When granted, run:
```bash
gh pr create --title "feat(checkout): per-store checkout flow" --body "$(cat <<'EOF'
## Summary
- Narrow `POST /api/v1/orders` to one store per submission with `store_id` + `payment_method`; response is a single Order.
- New `/checkout/[storeId]` page with address picker + payment-method radio.
- Cart page becomes a list with per-store "Checkout" CTAs; no global grand-total or address picker.
- `Payment.status` is always `Pending` so a future Razorpay webhook can flip it without UI rework.

## Test plan
- [ ] Backend: `uv run pytest -v`
- [ ] Backend lint+types: `uv run ruff check . && uv run mypy .`
- [ ] Frontend: `npm run lint && npm run build`
- [ ] Manual: two-store cart, checkout each separately, cart preserved between submissions
- [ ] Manual: direct `/checkout/<bogus-id>` redirects to `/cart`
EOF
)"
```
