<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Per-store-per-service Checkout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the existing per-store cart into per-store-per-service sub-baskets and promote checkout to operate on one `(store_id, service_id)` sub-basket at a time, producing one Order per service.

**Architecture:** `Cart` table gains a `service_id` column and its unique key becomes `(customer_profile_id, store_id, service_id)`. `Order` gains `service_id` + `service_name_snapshot`. Cart API + checkout service accept `service_id`; UI groups cart entries by store then by service and routes checkout to `/checkout/{storeId}/{serviceId}`. A single Alembic migration nukes transactional tables (cart, cartitem, order, orderitem, payment, delivery, review) and adds the columns — pre-launch, no live data to preserve.

**Tech Stack:** FastAPI 0.135 + SQLModel 0.0.37 + Alembic (asyncpg) on Postgres 15. Pytest + pytest-asyncio (real Postgres `khanabazaar_test`). Next.js 16 App Router + TypeScript on the frontend.

**Source spec:** `docs/superpowers/specs/2026-05-10-per-store-per-service-checkout-design.md`

---

## File Structure

**Backend — create:**
- `backend/app/migrations/versions/c1a7f5e9b3d2_per_store_per_service_checkout.py` — single Alembic migration: TRUNCATE transactional tables + add `cart.service_id` + `order.service_id` + `order.service_name_snapshot`
- `backend/app/tests/test_carts_per_service.py` — new tests for sub-basket cart routes
- `backend/app/tests/test_orders_per_service.py` — new tests for per-service order placement

**Backend — modify:**
- `backend/app/src/app/models/commerce.py` — add `service_id` to `Cart`, `service_id` + `service_name_snapshot` to `Order`, swap Cart unique key
- `backend/app/src/app/services/checkout.py` — rename `place_order_for_store` → `place_order_for_sub_basket`, add `_validate_service_active_for_store`, add service-mismatch invariant assertion against locked inventory, snapshot service name onto Order
- `backend/app/src/app/services/order_emails.py` — pass service name into email subject + body
- `backend/app/src/app/api/carts.py` — `_get_or_create_cart(profile_id, store_id, service_id)`; two-pronged validation in `POST /items`; replace `DELETE /{store_id}` with `DELETE /{store_id}/{service_id}`; sync drops mismatches as `service_mismatch`; serialize `service_id` + `service_name`
- `backend/app/src/app/api/orders.py` — `PlaceOrderRequest` gains `service_id`; pass through to renamed service; `_serialize_order` includes `service_id` + `service_name`; list filter `?service_id=` for customer
- `backend/app/src/app/schemas/carts.py` — `CartRead`, `CartItemAdd`, `CartSyncCart` gain `service_id` (+ `service_name` on read)
- `backend/app/src/app/schemas/orders.py` — `OrderRead`, `PlaceOrderRequest` gain `service_id` (+ `service_name` on read)
- `backend/app/src/app/worker.py` — `_load_order_email_context` returns `service_name_snapshot`; subject/body use it
- `backend/app/src/app/db/seed.py` — no-op verification (no demo carts/orders today; if any are added, attach `service_id` + `service_name_snapshot`)
- `backend/app/tests/test_carts.py`, `backend/app/tests/test_orders.py`, `backend/app/tests/test_checkout.py` (if present), `backend/app/tests/test_orders_serviceability.py`, `backend/app/tests/test_order_emails.py` — payloads pick up `service_id`, expected responses include `service_id` + `service_name`

**Frontend — create:**
- `frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.tsx` — relocated checkout page parameterized on `(storeId, serviceId)`
- `frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.module.css` — copy of the existing checkout CSS module

**Frontend — modify:**
- `frontend/src/types/index.ts` — `Cart` gains `service_id` + `service_name`; `Order` gains `service_id` + `service_name`
- `frontend/src/lib/localCart.ts` — composite `(storeId, serviceId)` keying; storage key bumped to `kb_carts_v2`; mutator signatures pick up `serviceId` (+ `serviceName` for `addToCart`); v1→v2 one-shot purge on first read
- `frontend/src/lib/remoteCart.ts` — `addItem`, `syncCarts` payloads include `service_id`; `clearStoreCart` → `clearSubBasket(token, storeId, serviceId)`; remote types include `service_id` + `service_name`
- `frontend/src/lib/CartContext.tsx` — mutator signatures pick up `serviceId` (+ `serviceName` for add); `findRemoteItemId` keys on `(storeId, serviceId, productId)`; rename `clearStoreCart` → `clearSubBasket`
- `frontend/src/app/(customer)/[locale]/cart/page.tsx` — outer group by store, inner section per service with per-service checkout CTA routing to `/checkout/{storeId}/{serviceId}`
- `frontend/src/components/ProductCard.tsx` — accept `serviceId` + `serviceName` props; thread into `addItem`
- `frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx` — pass active service's `(id, name)` to each `<ProductCard>`
- `frontend/src/components/CartRail.tsx` — accept optional `serviceId`; checkout button routes to `/checkout/{storeId}/{serviceId}` when both are present
- `frontend/src/app/(customer)/[locale]/checkout/[storeId]/page.tsx` — DELETE (replaced by `[storeId]/[serviceId]` route)
- `frontend/src/app/(customer)/[locale]/checkout/[storeId]/page.module.css` — DELETE

**Docs — modify:**
- `docs/flows.md` — replace the per-store-checkout narrative with the per-store-per-service version
- `CLAUDE.md` — update the Cart unique-key note + the per-store-checkout bullet under "Non-obvious patterns / gotchas"

---

## Conventions for this plan

- **TDD where possible.** Backend changes that produce observable behavior (route response shape, error codes, service-validation rejections) get a failing test first. Pure data-model column additions and schema-renames are exercised through the existing fixtures + a follow-up test, since `create_all` runs every test and there is no separate "table exists" assertion to write up-front.
- **Commit cadence.** One commit per task. Subject line uses Conventional Commits (`feat:`, `chore:`, `test:`, `docs:`, `refactor:`, `fix:`). No squashing later; each task lands a green test suite.
- **Test runner.** `uv run pytest backend/app/tests/<file>.py -v` from `backend/app/`. The `khanabazaar_test` Postgres DB must be running (`docker-compose up -d` first).
- **Frontend smoke.** No frontend test suite exists. Each FE task ends with `npm run lint` from `frontend/` and a brief manual-verification note for the reviewer.

---

## Task 1: Add `service_id` to `Cart`, `service_id` + `service_name_snapshot` to `Order`

**Files:**
- Modify: `backend/app/src/app/models/commerce.py`

- [ ] **Step 1: Update the Cart model**

Replace the existing `Cart` class with:

```python
class Cart(BaseSchema, table=True):
    __table_args__ = (
        UniqueConstraint(
            "customer_profile_id", "store_id", "service_id",
            name="uq_cart_customer_store_service",
        ),
    )
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False)
    store_id: int = Field(foreign_key="store.id", nullable=False)
    service_id: int = Field(foreign_key="service.id", nullable=False, index=True)
```

- [ ] **Step 2: Update the Order model**

Add two fields immediately after `store_id` in the existing `Order` class. Final state of the field block:

```python
class Order(BaseSchema, table=True):
    __tablename__ = "order"
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False, index=True)
    store_id: int = Field(foreign_key="store.id", nullable=False, index=True)
    service_id: int = Field(foreign_key="service.id", nullable=False, index=True)
    service_name_snapshot: str = Field(nullable=False)
    delivery_address_id: int = Field(foreign_key="address.id", nullable=False)
    status: OrderStatus = Field(default=OrderStatus.Pending, nullable=False, index=True)
    subtotal: float = Field(nullable=False)
    delivery_fee: float = Field(nullable=False)
    tax: float = Field(nullable=False)
    total: float = Field(nullable=False)
    delivery_address_snapshot: str = Field(nullable=False)
    placed_at: datetime = Field(  # type: ignore[call-overload]
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
```

- [ ] **Step 3: Verify type-check passes**

Run from `backend/app/`:

```bash
uv run mypy src/app/models/commerce.py
```

Expected: Success. No issues reported.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/models/commerce.py
git commit -m "feat(models): add service_id to Cart and Order"
```

---

## Task 2: Alembic migration for the schema change

**Files:**
- Create: `backend/app/migrations/versions/c1a7f5e9b3d2_per_store_per_service_checkout.py`

- [ ] **Step 1: Create the migration file**

Write the file with this exact contents:

```python
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""per_store_per_service_checkout

Revision ID: c1a7f5e9b3d2
Revises: cecb3aa39b17
Create Date: 2026-05-10 20:00:00.000000

Pre-launch nuke of transactional tables (cart, cartitem, order, orderitem,
payment, delivery, review) so we can introduce NOT NULL service columns
without writing a backfill. Add `service_id` to Cart, `service_id` plus
`service_name_snapshot` to Order, and replace the Cart unique key.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1a7f5e9b3d2"
down_revision: Union[str, Sequence[str], None] = "cecb3aa39b17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Wipe transactional data. Pre-launch only — there is no production
    #    customer cart or order data to preserve.
    op.execute(
        "TRUNCATE TABLE review, payment, delivery, orderitem, \"order\", "
        "cartitem, cart RESTART IDENTITY CASCADE"
    )

    # 2. Cart: swap unique key and add service_id FK + index.
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

    # 3. Order: add service_id FK + index and frozen service name snapshot.
    op.add_column("order", sa.Column("service_id", sa.Integer(), nullable=False))
    op.add_column(
        "order", sa.Column("service_name_snapshot", sa.String(), nullable=False)
    )
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

- [ ] **Step 2: Run the migration locally**

From `backend/app/`:

```bash
uv run alembic upgrade head
```

Expected output ends with `Running upgrade cecb3aa39b17 -> c1a7f5e9b3d2, per_store_per_service_checkout`. Confirm by inspecting `alembic_version`:

```bash
docker exec -it $(docker compose ps -q postgres) psql -U postgres -d khanabazaar -c "SELECT version_num FROM alembic_version;"
```

Expected: `c1a7f5e9b3d2`.

- [ ] **Step 3: Confirm the downgrade also runs cleanly**

```bash
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: both commands succeed; final version is `c1a7f5e9b3d2` again.

- [ ] **Step 4: Commit**

```bash
git add backend/app/migrations/versions/c1a7f5e9b3d2_per_store_per_service_checkout.py
git commit -m "feat(migrations): cart+order service columns, truncate transactional tables"
```

---

## Task 3: Cart + order schema DTOs accept and emit service fields

**Files:**
- Modify: `backend/app/src/app/schemas/carts.py`
- Modify: `backend/app/src/app/schemas/orders.py`

- [ ] **Step 1: Update cart schemas**

Replace the body of `backend/app/src/app/schemas/carts.py` after the imports block with:

```python
class CartItemRead(BaseModel):
    id: int
    inventory_id: int
    product_id: int
    product_name: str
    unit_price: float
    quantity: int
    line_total: float


class CartRead(BaseModel):
    store_id: int
    store_name: str
    service_id: int
    service_name: str
    items: List[CartItemRead]
    subtotal: float


class CartListResponse(BaseModel):
    carts: List[CartRead]


class CartItemAdd(BaseModel):
    store_id: int
    service_id: int = Field(gt=0)
    inventory_id: int
    quantity: int = Field(gt=0)


class CartItemUpdate(BaseModel):
    quantity: int = Field(gt=0)


class CartSyncItem(BaseModel):
    inventory_id: int
    quantity: int = Field(gt=0)


class CartSyncCart(BaseModel):
    store_id: int
    service_id: int = Field(gt=0)
    items: List[CartSyncItem]


class CartSyncRequest(BaseModel):
    carts: List[CartSyncCart]


class DroppedSyncItem(BaseModel):
    inventory_id: int
    reason: str


class CartSyncResponse(BaseModel):
    carts: List[CartRead]
    dropped: List[DroppedSyncItem]
```

- [ ] **Step 2: Update order schemas**

In `backend/app/src/app/schemas/orders.py`, add `service_id` + `service_name` to `OrderRead` and `service_id` to `PlaceOrderRequest`:

```python
class OrderRead(BaseModel):
    id: int
    store_id: int
    store_name: str
    service_id: int
    service_name: str
    customer_name: Optional[str] = None
    status: OrderStatus
    subtotal: float
    delivery_fee: float
    tax: float
    total: float
    placed_at: datetime
    delivery_address_snapshot: str
    items: List[OrderItemRead]
    payment: PaymentRead
    delivery: DeliveryRead


# ...

class PlaceOrderRequest(BaseModel):
    customer_address_id: int = Field(gt=0)
    store_id: int = Field(gt=0)
    service_id: int = Field(gt=0)
    payment_method: PaymentMethod
```

- [ ] **Step 3: Verify type-check passes**

```bash
cd backend/app && uv run mypy src/app/schemas/carts.py src/app/schemas/orders.py
```

Expected: success.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/schemas/carts.py backend/app/src/app/schemas/orders.py
git commit -m "feat(schemas): cart+order DTOs gain service_id and service_name"
```

---

## Task 4: Service-name lookup helper for cart serialization

**Files:**
- Modify: `backend/app/src/app/api/carts.py`

- [ ] **Step 1: Add an English service-name resolver**

In `backend/app/src/app/api/carts.py`, add this helper directly under the existing `_product_names` function:

```python
async def _service_names(
    session: AsyncSession, service_ids: list[int]
) -> dict[int, str]:
    """Map service_id → display name. English translation, slug fallback."""
    if not service_ids:
        return {}
    from app.models.catalog import Service, ServiceTranslation

    result = await session.exec(
        select(Service.id, Service.slug, ServiceTranslation.name)
        .join(  # type: ignore[arg-type]
            ServiceTranslation,
            (ServiceTranslation.service_id == Service.id)
            & (ServiceTranslation.language_code == DEFAULT_LANG),
            isouter=True,
        )
        .where(Service.id.in_(service_ids))  # type: ignore[union-attr]
    )
    return {
        sid: (name or slug)
        for sid, slug, name in result.all()
        if sid is not None
    }
```

- [ ] **Step 2: Verify import resolves**

```bash
cd backend/app && uv run python -c "from app.api.carts import _service_names; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/src/app/api/carts.py
git commit -m "refactor(carts): add _service_names helper for sub-basket serialization"
```

---

## Task 5: Cart routes serialize and accept `service_id`

**Files:**
- Modify: `backend/app/src/app/api/carts.py`

- [ ] **Step 1: Update `_get_or_create_cart` signature**

Replace the existing `_get_or_create_cart` with:

```python
async def _get_or_create_cart(
    session: AsyncSession,
    customer_profile_id: int,
    store_id: int,
    service_id: int,
) -> Cart:
    result = await session.exec(
        select(Cart).where(
            Cart.customer_profile_id == customer_profile_id,
            Cart.store_id == store_id,
            Cart.service_id == service_id,
        )
    )
    cart = result.first()
    if cart is None:
        # Validate store exists + active.
        store_result = await session.exec(select(Store).where(Store.id == store_id))
        store = store_result.first()
        if store is None or not store.is_active:
            raise HTTPException(status_code=404, detail="Store not found or inactive")
        cart = Cart(
            customer_profile_id=customer_profile_id,
            store_id=store_id,
            service_id=service_id,
        )
        session.add(cart)
        await session.flush()
    return cart
```

- [ ] **Step 2: Serialize `service_id` + `service_name`**

Replace `_serialize_carts` with:

```python
async def _serialize_carts(session: AsyncSession, carts: list[Cart]) -> list[CartRead]:
    if not carts:
        return []
    cart_ids = [c.id for c in carts if c.id is not None]
    item_result = await session.exec(
        select(CartItem, StoreInventory, MasterProduct, Store)
        .join(StoreInventory, StoreInventory.id == CartItem.inventory_id)  # type: ignore[arg-type]
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .join(Store, Store.id == StoreInventory.store_id)  # type: ignore[arg-type]
        .where(CartItem.cart_id.in_(cart_ids))  # type: ignore[attr-defined]
    )
    rows = list(item_result.all())
    by_cart: dict[int, list[tuple[CartItem, StoreInventory, MasterProduct, Store]]] = {}
    product_ids: set[int] = set()
    for item, inv, product, store in rows:
        by_cart.setdefault(item.cart_id, []).append((item, inv, product, store))
        if product.id is not None:
            product_ids.add(product.id)

    name_by_product = await _product_names(session, list(product_ids))
    name_by_service = await _service_names(session, [c.service_id for c in carts])

    out: list[CartRead] = []
    for cart in carts:
        assert cart.id is not None
        rows_for_cart = by_cart.get(cart.id, [])
        items: list[CartItemRead] = []
        for item, inv, product, _ in rows_for_cart:
            assert item.id is not None
            assert inv.id is not None
            assert product.id is not None
            items.append(CartItemRead(
                id=item.id,
                inventory_id=inv.id,
                product_id=product.id,
                product_name=name_by_product.get(product.id, product.slug),
                unit_price=inv.price,
                quantity=item.quantity,
                line_total=inv.price * item.quantity,
            ))
        store_name = rows_for_cart[0][3].name if rows_for_cart else ""
        if not store_name:
            store_result = await session.exec(select(Store).where(Store.id == cart.store_id))
            store_row = store_result.first()
            store_name = store_row.name if store_row else ""
        out.append(
            CartRead(
                store_id=cart.store_id,
                store_name=store_name,
                service_id=cart.service_id,
                service_name=name_by_service.get(cart.service_id, str(cart.service_id)),
                items=items,
                subtotal=sum(i.line_total for i in items),
            )
        )
    return out
```

- [ ] **Step 3: Run the test suite to confirm nothing else broke yet**

```bash
cd backend/app && uv run pytest tests/test_carts.py -v
```

Expected: many failures from missing `service_id` in payloads — that is the next task. The router import must succeed; check the very first error is a payload-validation failure, not an `ImportError`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/api/carts.py
git commit -m "feat(carts): serialize service_id and service_name on cart reads"
```

---

## Task 6: `POST /carts/items` validates the two-pronged service contract

**Files:**
- Modify: `backend/app/src/app/api/carts.py`

- [ ] **Step 1: Add the validation helper**

Add directly below `_get_or_create_cart`:

```python
async def _validate_service_for_store(
    session: AsyncSession, store_id: int, service_id: int
) -> None:
    """Raise 409 service_unavailable if the store's seller does not offer
    `service_id`, or if Service.is_active is false."""
    from app.models.catalog import Service
    from app.models.profile import SellerProfile, SellerProfileService

    row = (
        await session.exec(
            select(SellerProfileService.id)
            .join(  # type: ignore[arg-type]
                SellerProfile,
                SellerProfile.id == SellerProfileService.seller_profile_id,
            )
            .join(Store, Store.seller_profile_id == SellerProfile.id)  # type: ignore[arg-type]
            .where(
                Store.id == store_id,
                SellerProfileService.service_id == service_id,
            )
        )
    ).first()
    service_active = (
        await session.exec(
            select(Service.is_active).where(Service.id == service_id)
        )
    ).first()
    if row is None or service_active is not True:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "service_unavailable",
                "store_id": store_id,
                "service_id": service_id,
            },
        )


async def _assert_inventory_service_match(
    session: AsyncSession, inventory_id: int, service_id: int
) -> None:
    """Raise 400 service_mismatch if `inventory_id`'s product resolves to a
    different `service_id` via subcategory→category."""
    from app.models.catalog import Category, Subcategory

    resolved = (
        await session.exec(
            select(Category.service_id)
            .join(Subcategory, Subcategory.category_id == Category.id)  # type: ignore[arg-type]
            .join(MasterProduct, MasterProduct.subcategory_id == Subcategory.id)  # type: ignore[arg-type]
            .join(StoreInventory, StoreInventory.product_id == MasterProduct.id)  # type: ignore[arg-type]
            .where(StoreInventory.id == inventory_id)
        )
    ).first()
    if resolved != service_id:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "service_mismatch",
                "inventory_id": inventory_id,
                "service_id": service_id,
            },
        )
```

- [ ] **Step 2: Rewrite `add_cart_item` to call them in order**

Replace `add_cart_item` with:

```python
@router.post("/items", response_model=CartItemRead)
async def add_cart_item(
    payload: CartItemAdd,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> CartItemRead:
    profile_id = await _customer_profile_id(session, user)

    inv_result = await session.exec(
        select(StoreInventory).where(StoreInventory.id == payload.inventory_id)
    )
    inv = inv_result.first()
    if inv is None:
        raise HTTPException(status_code=404, detail="Inventory not found")
    if inv.store_id != payload.store_id:
        raise HTTPException(status_code=400, detail="inventory_store_mismatch")
    if not inv.is_available:
        raise HTTPException(status_code=409, detail="item_unavailable")

    await _validate_service_for_store(session, payload.store_id, payload.service_id)
    await _assert_inventory_service_match(
        session, payload.inventory_id, payload.service_id
    )

    cart = await _get_or_create_cart(
        session, profile_id, payload.store_id, payload.service_id
    )
    existing_result = await session.exec(
        select(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.inventory_id == payload.inventory_id,
        )
    )
    item = existing_result.first()
    updated = item is not None
    if item is None:
        item = CartItem(
            cart_id=cart.id, inventory_id=payload.inventory_id, quantity=payload.quantity
        )
        session.add(item)
    else:
        item.quantity += payload.quantity
    await session.commit()
    await session.refresh(item)

    response.status_code = status.HTTP_200_OK if updated else status.HTTP_201_CREATED
    return await _build_cart_item_response(session, item)
```

- [ ] **Step 3: Confirm the type-check passes**

```bash
cd backend/app && uv run mypy src/app/api/carts.py
```

Expected: success.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/api/carts.py
git commit -m "feat(carts): two-pronged service validation on add_cart_item"
```

---

## Task 7: `DELETE /carts/{store_id}/{service_id}` replaces `DELETE /carts/{store_id}`

**Files:**
- Modify: `backend/app/src/app/api/carts.py`

- [ ] **Step 1: Replace the clear-cart route**

Replace the existing `clear_store_cart` route with:

```python
@router.delete("/{store_id}/{service_id}", status_code=204)
async def clear_sub_basket_cart(
    store_id: int,
    service_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> Response:
    profile_id = await _customer_profile_id(session, user)
    cart_result = await session.exec(
        select(Cart).where(
            Cart.customer_profile_id == profile_id,
            Cart.store_id == store_id,
            Cart.service_id == service_id,
        )
    )
    cart = cart_result.first()
    if cart is not None:
        items_result = await session.exec(select(CartItem).where(CartItem.cart_id == cart.id))
        for item in items_result.all():
            await session.delete(item)
        await session.flush()
        await session.delete(cart)
        await session.commit()
    return Response(status_code=204)
```

- [ ] **Step 2: Confirm the FastAPI app still imports cleanly**

```bash
cd backend/app && uv run python -c "from app import app; print(sorted(r.path for r in app.routes if r.path.startswith('/api/v1/carts')))"
```

Expected output contains `/api/v1/carts/{store_id}/{service_id}` and **does not** contain `/api/v1/carts/{store_id}`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/src/app/api/carts.py
git commit -m "feat(carts): clear-cart route keyed on (store_id, service_id)"
```

---

## Task 8: `POST /carts/sync` drops service-mismatches and writes `service_id`

**Files:**
- Modify: `backend/app/src/app/api/carts.py`

- [ ] **Step 1: Rewrite the sync handler**

Replace the existing `sync_carts` route with:

```python
@router.post("/sync", response_model=CartSyncResponse)
async def sync_carts(
    payload: CartSyncRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> CartSyncResponse:
    # TODO(perf): batch Store and StoreInventory lookups across the whole
    # payload before scaling sync beyond MVP-sized carts.
    profile_id = await _customer_profile_id(session, user)
    dropped: list[DroppedSyncItem] = []

    for cart_payload in payload.carts:
        store_result = await session.exec(
            select(Store).where(Store.id == cart_payload.store_id)
        )
        store = store_result.first()
        if store is None or not store.is_active:
            for it in cart_payload.items:
                dropped.append(DroppedSyncItem(
                    inventory_id=it.inventory_id, reason="store_unavailable",
                ))
            continue

        try:
            await _validate_service_for_store(
                session, cart_payload.store_id, cart_payload.service_id
            )
        except HTTPException:
            for it in cart_payload.items:
                dropped.append(DroppedSyncItem(
                    inventory_id=it.inventory_id, reason="service_unavailable",
                ))
            continue

        cart: Cart | None = None

        for item_payload in cart_payload.items:
            inv_result = await session.exec(
                select(StoreInventory).where(StoreInventory.id == item_payload.inventory_id)
            )
            inv = inv_result.first()
            if inv is None or inv.store_id != cart_payload.store_id or not inv.is_available:
                dropped.append(DroppedSyncItem(
                    inventory_id=item_payload.inventory_id,
                    reason="unknown_inventory" if inv is None else "item_unavailable",
                ))
                continue

            try:
                await _assert_inventory_service_match(
                    session, item_payload.inventory_id, cart_payload.service_id
                )
            except HTTPException:
                dropped.append(DroppedSyncItem(
                    inventory_id=item_payload.inventory_id, reason="service_mismatch",
                ))
                continue

            if cart is None:
                cart = await _get_or_create_cart(
                    session, profile_id, cart_payload.store_id, cart_payload.service_id
                )

            existing_result = await session.exec(
                select(CartItem).where(
                    CartItem.cart_id == cart.id,
                    CartItem.inventory_id == item_payload.inventory_id,
                )
            )
            existing = existing_result.first()
            if existing is None:
                session.add(CartItem(
                    cart_id=cart.id,
                    inventory_id=item_payload.inventory_id,
                    quantity=item_payload.quantity,
                ))
            else:
                existing.quantity += item_payload.quantity

    await session.commit()

    result = await session.exec(
        select(Cart).where(Cart.customer_profile_id == profile_id)
    )
    carts = list(result.all())
    return CartSyncResponse(
        carts=await _serialize_carts(session, carts),
        dropped=dropped,
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/src/app/api/carts.py
git commit -m "feat(carts): sync drops service-mismatched items and writes service_id"
```

---

## Task 9: Update `test_carts.py` to thread `service_id` through every payload

**Files:**
- Modify: `backend/app/tests/test_carts.py`

- [ ] **Step 1: Walk the file**

Read `backend/app/tests/test_carts.py` in full. Note every `_seed_product` call — `_seed_product` already creates a Service row for each test product, so it already has a `service_id` on the chain. Cache it for assertions.

- [ ] **Step 2: Thread `service_id` through the fixture**

In `_seed_product`, change the return to include the Service ID so tests can use it. Update the return type and add:

```python
async def _seed_product(
    session: AsyncSession, *, service_slug: str, category_slug: str,
    subcategory_slug: str, product_slug: str, name: str, base_price: float,
) -> tuple[MasterProduct, int]:
    # ... unchanged body until the return ...
    return product, service.id
```

Update each call site at the top of the file: replace `product = await _seed_product(...)` with `product, service_id = await _seed_product(...)`. The fixture should `yield {"service_id": service_id, ...}` so tests can reach it.

- [ ] **Step 3: Thread `service_id` into every `POST /carts/items` payload**

In every cart `client.post("/api/v1/carts/items", json={...})` call, add `"service_id": service_id` next to `"store_id"`. Similarly add `"service_id"` to each `CartSyncCart` body inside `POST /carts/sync`.

- [ ] **Step 4: Update `DELETE` test paths**

Replace `client.delete(f"/api/v1/carts/{store_id}")` with `client.delete(f"/api/v1/carts/{store_id}/{service_id}")`.

- [ ] **Step 5: Update expected response shapes**

In every assertion against the cart list response, expect the body to contain `service_id` and `service_name` per cart entry. For `addToCart` assertions, the `service_unavailable` and `service_mismatch` codes are *not* expected from existing tests — keep existing assertions; introduce them only in the new file (Task 11).

- [ ] **Step 6: Run the test**

```bash
cd backend/app && uv run pytest tests/test_carts.py -v
```

Expected: all passing. If a test fails because `_seed_product` is also imported from `test_orders.py`, update that import too — both tests use the same helper.

- [ ] **Step 7: Commit**

```bash
git add backend/app/tests/test_carts.py
git commit -m "test(carts): thread service_id through cart api tests"
```

---

## Task 10: Update `test_orders.py` fixtures so existing tests still pass

**Files:**
- Modify: `backend/app/tests/test_orders.py`

- [ ] **Step 1: Adapt to the new `_seed_product` return**

Update the `await _seed_product(...)` site in `test_orders.py` to `product, service_id = await _seed_product(...)`. Bind the `service_id` onto the seller via a `SellerProfileService` row so the new service-validation in checkout (Task 12) does not reject the order, and persist a default `Service` row on the seller's offered services list.

- [ ] **Step 2: Thread `service_id` into every `PlaceOrderRequest`**

In every `client.post("/api/v1/orders", json={...})` payload, add `"service_id": service_id`. In every `OrderRead` assertion, expect `service_id` and `service_name` in the returned body.

- [ ] **Step 3: Bind the customer's cart to the new shape**

Where the fixture pre-creates a `Cart(...)`, pass `service_id=service_id`. When a test later builds an `Order(...)` directly, also pass `service_id=service_id` and `service_name_snapshot=service_name`.

- [ ] **Step 4: Run the test**

```bash
cd backend/app && uv run pytest tests/test_orders.py -v
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tests/test_orders.py
git commit -m "test(orders): thread service_id through order api tests"
```

---

## Task 11: New test file `test_carts_per_service.py`

**Files:**
- Create: `backend/app/tests/test_carts_per_service.py`

- [ ] **Step 1: Sketch the fixture set**

Create the file with these exact sections. The seed function creates one customer, one seller, one store, and TWO services (Grocery + Pharmacy) each with one product. The seller's `SellerProfileService` rows include both services.

```python
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category, CategoryTranslation, MasterProduct, MasterProductTranslation,
    Service, ServiceTranslation, Subcategory, SubcategoryTranslation,
)
from app.models.commerce import Cart, CartItem
from app.models.profile import (
    CustomerProfile, SellerProfile, SellerProfileService, VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address


mock_customer = User(id=401, email="psv-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=402, email="psv-seller@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    for u in (mock_customer, mock_seller):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer = CustomerProfile(user_id=mock_customer.id, first_name="C")
    session.add(customer)
    await session.flush()

    seller_addr = Address(**make_address(pincode="560200"))
    session.add(seller_addr)
    await session.flush()
    seller = SellerProfile(
        user_id=mock_seller.id, first_name="S", phone="+919811000001",
        business_name="X", bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_addr.id,
    )
    session.add(seller)
    await session.flush()

    store_addr = Address(**make_address(pincode="560201"))
    session.add(store_addr)
    await session.flush()
    store = Store(name="Store", seller_profile_id=seller.id, address_id=store_addr.id)
    session.add(store)
    await session.flush()

    grocery = Service(slug="grocery")
    pharmacy = Service(slug="pharmacy")
    other_service = Service(slug="bakery")  # NOT offered by seller
    session.add_all([grocery, pharmacy, other_service])
    await session.flush()
    session.add_all([
        ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"),
        ServiceTranslation(service_id=pharmacy.id, language_code="en", name="Pharmacy"),
        ServiceTranslation(service_id=other_service.id, language_code="en", name="Bakery"),
    ])
    await session.flush()

    session.add_all([
        SellerProfileService(seller_profile_id=seller.id, service_id=grocery.id),
        SellerProfileService(seller_profile_id=seller.id, service_id=pharmacy.id),
    ])
    await session.flush()

    async def _add_inventory(svc: Service, slug: str, name: str, price: float) -> StoreInventory:
        category = Category(service_id=svc.id, slug=f"{slug}-cat")
        session.add(category)
        await session.flush()
        session.add(CategoryTranslation(
            category_id=category.id, language_code="en", name=f"{name}-cat",
        ))
        subcat = Subcategory(category_id=category.id, slug=f"{slug}-sub")
        session.add(subcat)
        await session.flush()
        session.add(SubcategoryTranslation(
            subcategory_id=subcat.id, language_code="en", name=f"{name}-sub",
        ))
        product = MasterProduct(subcategory_id=subcat.id, slug=slug, base_price=price)
        session.add(product)
        await session.flush()
        session.add(MasterProductTranslation(
            master_product_id=product.id, language_code="en", name=name, description=name,
        ))
        await session.flush()
        inv = StoreInventory(
            store_id=store.id, product_id=product.id, price=price, stock=10, is_available=True,
        )
        session.add(inv)
        await session.flush()
        return inv

    g_inv = await _add_inventory(grocery, "rice", "Rice", 50.0)
    p_inv = await _add_inventory(pharmacy, "paracetamol", "Paracetamol", 20.0)
    bakery_inv = await _add_inventory(other_service, "bread", "Bread", 30.0)
    # Note: bakery_inv is wired through the catalog but is NOT in the seller's
    # offered services — used to assert service_unavailable.

    await session.commit()

    yield {
        "store_id": store.id,
        "grocery_id": grocery.id,
        "pharmacy_id": pharmacy.id,
        "bakery_id": other_service.id,
        "grocery_inv_id": g_inv.id,
        "pharmacy_inv_id": p_inv.id,
        "bakery_inv_id": bakery_inv.id,
    }


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 2: Test `cross_service_add_creates_two_sub_baskets`**

Append to the test file:

```python
async def test_cross_service_add_creates_two_sub_baskets(
    client: AsyncClient, seed: dict[str, int]
) -> None:
    for inv_id, svc_id in (
        (seed["grocery_inv_id"], seed["grocery_id"]),
        (seed["pharmacy_inv_id"], seed["pharmacy_id"]),
    ):
        resp = await client.post(
            "/api/v1/carts/items",
            json={
                "store_id": seed["store_id"],
                "service_id": svc_id,
                "inventory_id": inv_id,
                "quantity": 1,
            },
        )
        assert resp.status_code in (200, 201), resp.text

    listing = await client.get("/api/v1/carts/")
    assert listing.status_code == 200
    carts = listing.json()["carts"]
    assert len(carts) == 2
    store_ids = {c["store_id"] for c in carts}
    svc_ids = {c["service_id"] for c in carts}
    assert store_ids == {seed["store_id"]}
    assert svc_ids == {seed["grocery_id"], seed["pharmacy_id"]}
```

- [ ] **Step 3: Test `service_not_offered_by_seller_is_409`**

```python
async def test_service_not_offered_by_seller_is_409(
    client: AsyncClient, seed: dict[str, int]
) -> None:
    resp = await client.post(
        "/api/v1/carts/items",
        json={
            "store_id": seed["store_id"],
            "service_id": seed["bakery_id"],
            "inventory_id": seed["bakery_inv_id"],
            "quantity": 1,
        },
    )
    assert resp.status_code == 409
    body = resp.json()["detail"]
    assert body["detail"] == "service_unavailable"
    assert body["service_id"] == seed["bakery_id"]
```

- [ ] **Step 4: Test `inventory_service_mismatch_is_400`**

```python
async def test_inventory_service_mismatch_is_400(
    client: AsyncClient, seed: dict[str, int]
) -> None:
    # Inventory belongs to grocery but payload claims pharmacy.
    resp = await client.post(
        "/api/v1/carts/items",
        json={
            "store_id": seed["store_id"],
            "service_id": seed["pharmacy_id"],
            "inventory_id": seed["grocery_inv_id"],
            "quantity": 1,
        },
    )
    assert resp.status_code == 400
    body = resp.json()["detail"]
    assert body["detail"] == "service_mismatch"
```

- [ ] **Step 5: Test `globally_inactive_service_is_409`**

```python
async def test_globally_inactive_service_is_409(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int]
) -> None:
    from sqlmodel import select
    grocery = (await session.exec(
        select(Service).where(Service.id == seed["grocery_id"])
    )).first()
    assert grocery is not None
    grocery.is_active = False
    await session.commit()

    resp = await client.post(
        "/api/v1/carts/items",
        json={
            "store_id": seed["store_id"],
            "service_id": seed["grocery_id"],
            "inventory_id": seed["grocery_inv_id"],
            "quantity": 1,
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["detail"] == "service_unavailable"
```

- [ ] **Step 6: Test `delete_sub_basket_leaves_sibling`**

```python
async def test_delete_sub_basket_leaves_sibling(
    client: AsyncClient, seed: dict[str, int]
) -> None:
    for inv_id, svc_id in (
        (seed["grocery_inv_id"], seed["grocery_id"]),
        (seed["pharmacy_inv_id"], seed["pharmacy_id"]),
    ):
        await client.post(
            "/api/v1/carts/items",
            json={
                "store_id": seed["store_id"],
                "service_id": svc_id,
                "inventory_id": inv_id,
                "quantity": 1,
            },
        )

    dele = await client.delete(
        f"/api/v1/carts/{seed['store_id']}/{seed['grocery_id']}"
    )
    assert dele.status_code == 204

    listing = (await client.get("/api/v1/carts/")).json()["carts"]
    assert len(listing) == 1
    assert listing[0]["service_id"] == seed["pharmacy_id"]
```

- [ ] **Step 7: Test `sync_filters_service_mismatch_into_dropped`**

```python
async def test_sync_filters_service_mismatch_into_dropped(
    client: AsyncClient, seed: dict[str, int]
) -> None:
    resp = await client.post(
        "/api/v1/carts/sync",
        json={
            "carts": [
                {
                    "store_id": seed["store_id"],
                    "service_id": seed["pharmacy_id"],
                    "items": [
                        {"inventory_id": seed["pharmacy_inv_id"], "quantity": 1},
                        {"inventory_id": seed["grocery_inv_id"], "quantity": 1},
                    ],
                },
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    dropped = body["dropped"]
    assert any(
        d["inventory_id"] == seed["grocery_inv_id"]
        and d["reason"] == "service_mismatch"
        for d in dropped
    )
    assert len(body["carts"]) == 1
    assert body["carts"][0]["service_id"] == seed["pharmacy_id"]
    assert {i["inventory_id"] for i in body["carts"][0]["items"]} == {
        seed["pharmacy_inv_id"]
    }
```

- [ ] **Step 8: Run the new test file**

```bash
cd backend/app && uv run pytest tests/test_carts_per_service.py -v
```

Expected: all six tests pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/tests/test_carts_per_service.py
git commit -m "test(carts): sub-basket auto-split, service validation, sync drops"
```

---

## Task 12: Checkout service operates on `(store_id, service_id)` sub-baskets

**Files:**
- Modify: `backend/app/src/app/services/checkout.py`

- [ ] **Step 1: Rename and re-key the cart loader**

Replace `_load_cart_for_store` with:

```python
async def _load_cart_for_sub_basket(
    session: AsyncSession,
    customer_profile_id: int,
    store_id: int,
    service_id: int,
) -> tuple[Cart, list[CartItem]]:
    """Return (cart, items) for the customer's (store, service) sub-basket.
    Raises 404 cart_not_found if no row; 400 cart_empty if items list is empty."""
    cart_result = await session.exec(
        select(Cart).where(
            Cart.customer_profile_id == customer_profile_id,
            Cart.store_id == store_id,
            Cart.service_id == service_id,
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

- [ ] **Step 2: Add the service-active-for-store validator**

Add directly below `_validate_stores_active`:

```python
async def _validate_service_active_for_store(
    session: AsyncSession, store_id: int, service_id: int
) -> None:
    """Raise 409 service_unavailable if seller no longer offers `service_id`
    or if `Service.is_active` is false."""
    from app.models.catalog import Service
    from app.models.profile import SellerProfile, SellerProfileService

    row = (
        await session.exec(
            select(SellerProfileService.id)
            .join(  # type: ignore[arg-type]
                SellerProfile,
                SellerProfile.id == SellerProfileService.seller_profile_id,
            )
            .join(Store, Store.seller_profile_id == SellerProfile.id)  # type: ignore[arg-type]
            .where(
                Store.id == store_id,
                SellerProfileService.service_id == service_id,
            )
        )
    ).first()
    active = (
        await session.exec(select(Service.is_active).where(Service.id == service_id))
    ).first()
    if row is None or active is not True:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "service_unavailable",
                "store_id": store_id,
                "service_id": service_id,
            },
        )


async def _assert_locked_inventory_matches_service(
    session: AsyncSession, locked_inv_ids: list[int], service_id: int
) -> None:
    """After lock, assert every locked inventory's product resolves to
    `service_id` via subcategory→category. Drift since add-to-cart raises
    409 service_mismatch with the first offending inventory_id."""
    from app.models.catalog import Category, Subcategory

    rows = (
        await session.exec(
            select(StoreInventory.id, Category.service_id)
            .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
            .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
            .join(Category, Category.id == Subcategory.category_id)  # type: ignore[arg-type]
            .where(StoreInventory.id.in_(locked_inv_ids))  # type: ignore[union-attr]
        )
    ).all()
    for inv_id, resolved in rows:
        if resolved != service_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "detail": "service_mismatch",
                    "inventory_id": inv_id,
                    "service_id": service_id,
                },
            )
```

- [ ] **Step 3: Add the service-name snapshot helper**

Add below `_snapshot_product_names`:

```python
async def _snapshot_service_name(
    session: AsyncSession, service_id: int
) -> str:
    """English service name; falls back to slug when no `en` translation."""
    from app.models.catalog import Service, ServiceTranslation

    row = (
        await session.exec(
            select(Service.slug, ServiceTranslation.name)
            .join(  # type: ignore[arg-type]
                ServiceTranslation,
                (ServiceTranslation.service_id == Service.id)
                & (ServiceTranslation.language_code == "en"),
                isouter=True,
            )
            .where(Service.id == service_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="service_not_found")
    slug, name = row
    return name or slug
```

- [ ] **Step 4: Rebuild `place_order_for_sub_basket`**

Replace `place_order_for_store` (function) with:

```python
async def place_order_for_sub_basket(
    session: AsyncSession,
    user: User,
    customer_address_id: int,
    store_id: int,
    service_id: int,
    payment_method: PaymentMethod,
) -> Order:
    profile = await _customer_profile(session, user)
    assert profile.id is not None

    address_id, address_snapshot = await _resolve_address(
        session, customer_address_id, profile.id
    )

    await _validate_service_active_for_store(session, store_id, service_id)

    cart, cart_items = await _load_cart_for_sub_basket(
        session, profile.id, store_id, service_id
    )

    await _assert_serviceable(session, store_id=store_id, address_id=address_id)

    inv_ids = [item.inventory_id for item in cart_items]
    locked_inv = await lock_inventory_rows(session, inv_ids)
    inv_by_id: dict[int, StoreInventory] = {
        inv.id: inv for inv in locked_inv if inv.id is not None
    }

    _validate_inventory_availability(cart_items, inv_by_id)
    await _validate_stores_active(session, [store_id])
    await _assert_locked_inventory_matches_service(session, inv_ids, service_id)

    name_by_inv = await _snapshot_product_names(session, inv_ids)
    service_name_snapshot = await _snapshot_service_name(session, service_id)

    order, order_items, payment, delivery = _build_order_for_cart(
        profile_id=profile.id, address_id=address_id,
        address_snapshot=address_snapshot, cart=cart, items=cart_items,
        inv_by_id=inv_by_id, name_by_inv=name_by_inv,
        payment_method=payment_method,
        service_id=service_id, service_name_snapshot=service_name_snapshot,
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

    for item in cart_items:
        await session.delete(item)
    await session.flush()
    await session.delete(cart)

    await session.commit()
    await session.refresh(order)
    return order
```

- [ ] **Step 5: Update the builder signature**

Change the head of `_build_order_for_cart` to:

```python
def _build_order_for_cart(
    *, profile_id: int, address_id: int, address_snapshot: str,
    cart: Cart, items: list[CartItem],
    inv_by_id: dict[int, StoreInventory], name_by_inv: dict[int, str],
    payment_method: PaymentMethod,
    service_id: int, service_name_snapshot: str,
) -> tuple[Order, list[OrderItem], Payment, Delivery]:
```

And inside the function body, write `service_id` + `service_name_snapshot` onto the `Order(...)` instantiation:

```python
    order = Order(
        customer_profile_id=profile_id,
        store_id=cart.store_id,
        service_id=service_id,
        service_name_snapshot=service_name_snapshot,
        delivery_address_id=address_id,
        delivery_address_snapshot=address_snapshot,
        status=OrderStatus.Pending,
        subtotal=subtotal,
        delivery_fee=MVP_DELIVERY_FEE,
        tax=MVP_TAX,
        total=total,
    )
```

- [ ] **Step 6: Type-check**

```bash
cd backend/app && uv run mypy src/app/services/checkout.py
```

Expected: success.

- [ ] **Step 7: Commit**

```bash
git add backend/app/src/app/services/checkout.py
git commit -m "feat(checkout): place_order_for_sub_basket with service validation"
```

---

## Task 13: `POST /orders` wiring + serialization includes service fields

**Files:**
- Modify: `backend/app/src/app/api/orders.py`

- [ ] **Step 1: Update the imports**

Change the existing checkout import line to:

```python
from app.services.checkout import place_order_for_sub_basket
```

- [ ] **Step 2: Update the place_order handler**

Replace the existing `place_order` route with:

```python
@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=OrderRead, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def place_order(
    payload: PlaceOrderRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> OrderRead:
    order = await place_order_for_sub_basket(
        session,
        user,
        payload.customer_address_id,
        payload.store_id,
        payload.service_id,
        payload.payment_method,
    )
    if order.id is not None:
        dispatch_order_placed([order.id])
    return await _serialize_order(session, order, include_customer_name=False)
```

- [ ] **Step 3: Include service fields in `_serialize_order`**

Update the `return OrderRead(...)` block to:

```python
    return OrderRead(
        id=order.id,
        store_id=order.store_id,
        store_name=store.name if store else "",
        service_id=order.service_id,
        service_name=order.service_name_snapshot,
        customer_name=customer_name,
        status=order.status,
        subtotal=order.subtotal,
        delivery_fee=order.delivery_fee,
        tax=order.tax,
        total=order.total,
        placed_at=order.placed_at,
        delivery_address_snapshot=order.delivery_address_snapshot,
        items=[OrderItemRead(
            id=i.id,
            inventory_id=i.inventory_id,
            product_name_snapshot=i.product_name_snapshot,
            unit_price_snapshot=i.unit_price_snapshot,
            quantity=i.quantity,
            line_total=i.line_total,
        ) for i in items],
        payment=PaymentRead(
            method=payment.method, status=payment.status, amount=payment.amount, paid_at=payment.paid_at,
        ),
        delivery=DeliveryRead(
            status=delivery.status,
            packed_at=delivery.packed_at,
            dispatched_at=delivery.dispatched_at,
            delivered_at=delivery.delivered_at,
        ),
    )
```

- [ ] **Step 4: Add the optional service filter to the list route**

Update the `list_orders` signature and the customer branch:

```python
@router.get("", response_model=OrderListResponse)
@router.get("/", response_model=OrderListResponse, include_in_schema=False)
async def list_orders(
    status: Optional[str] = Query(default=None),
    service_id: Optional[int] = Query(default=None, gt=0),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderListResponse:
    statuses = _status_filter_for(status)
    stmt = select(Order)
    include_customer = False

    if user.role == UserRole.Customer:
        profile_result = await session.exec(
            select(CustomerProfile.id).where(CustomerProfile.user_id == user.id)
        )
        profile_id = profile_result.first()
        if profile_id is None:
            return OrderListResponse(orders=[])
        stmt = stmt.where(Order.customer_profile_id == profile_id)
        if service_id is not None:
            stmt = stmt.where(Order.service_id == service_id)
    elif user.role == UserRole.Seller:
        store_ids = await _seller_store_ids(session, user)
        if not store_ids:
            return OrderListResponse(orders=[])
        stmt = stmt.where(Order.store_id.in_(store_ids))  # type: ignore[attr-defined]
        include_customer = True
    elif user.role == UserRole.Admin:
        include_customer = True
    else:
        raise HTTPException(status_code=403, detail="forbidden")

    if statuses is not None:
        stmt = stmt.where(Order.status.in_(statuses))  # type: ignore[attr-defined]

    stmt = stmt.order_by(Order.placed_at.desc()).limit(50)  # type: ignore[attr-defined]
    result = await session.exec(stmt)
    orders = list(result.all())
    return OrderListResponse(
        orders=[await _serialize_order(session, o, include_customer_name=include_customer) for o in orders],
    )
```

Seller and admin queries do not gain a `service_id` filter in this spec — the optional query param is silently ignored for those roles.

- [ ] **Step 5: Type-check**

```bash
cd backend/app && uv run mypy src/app/api/orders.py
```

Expected: success.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/api/orders.py
git commit -m "feat(orders): plumb service_id through place_order and list filter"
```

---

## Task 14: New test file `test_orders_per_service.py`

**Files:**
- Create: `backend/app/tests/test_orders_per_service.py`

- [ ] **Step 1: Build the fixture**

Reuse the seed shape from Task 11 — one customer with a default `CustomerAddress`, one seller with both Grocery + Pharmacy, one store, two inventory rows (one per service). Also seed a `CustomerAddress` with `is_default=True` so order placement has somewhere to deliver.

Set the address coordinates close to the store address so `ST_DWithin` allows the order (e.g. both at the same lat/lng or within the default 5km radius). Reuse `make_address` and override `latitude` + `longitude` where needed.

```python
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category, CategoryTranslation, MasterProduct, MasterProductTranslation,
    Service, ServiceTranslation, Subcategory, SubcategoryTranslation,
)
from app.models.commerce import Cart, CartItem, Order
from app.models.profile import (
    CustomerAddress, CustomerProfile, SellerProfile, SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address


mock_customer = User(id=501, email="ops-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=502, email="ops-seller@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture(autouse=True)
async def patch_email_dispatch() -> AsyncGenerator[None, None]:
    with (
        patch("app.api.orders.dispatch_order_placed"),
        patch("app.api.orders.dispatch_order_status_changed"),
    ):
        yield


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    for u in (mock_customer, mock_seller):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer = CustomerProfile(user_id=mock_customer.id, first_name="C")
    session.add(customer)
    await session.flush()

    cust_addr = Address(
        **make_address(pincode="560300", latitude=12.9716, longitude=77.5946)
    )
    session.add(cust_addr)
    await session.flush()
    session.add(CustomerAddress(
        customer_profile_id=customer.id, address_id=cust_addr.id, is_default=True,
    ))

    seller_addr = Address(
        **make_address(pincode="560301", latitude=12.9716, longitude=77.5946)
    )
    session.add(seller_addr)
    await session.flush()
    seller = SellerProfile(
        user_id=mock_seller.id, first_name="S", phone="+919811000002",
        business_name="Shop", bank_account_number="2", bank_ifsc="HDFC0000002",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_addr.id,
    )
    session.add(seller)
    await session.flush()

    store_addr = Address(
        **make_address(pincode="560302", latitude=12.9716, longitude=77.5946)
    )
    session.add(store_addr)
    await session.flush()
    store = Store(name="Multi", seller_profile_id=seller.id, address_id=store_addr.id)
    session.add(store)
    await session.flush()

    grocery = Service(slug="grocery")
    pharmacy = Service(slug="pharmacy")
    session.add_all([grocery, pharmacy])
    await session.flush()
    session.add_all([
        ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"),
        ServiceTranslation(service_id=pharmacy.id, language_code="en", name="Pharmacy"),
    ])
    session.add_all([
        SellerProfileService(seller_profile_id=seller.id, service_id=grocery.id),
        SellerProfileService(seller_profile_id=seller.id, service_id=pharmacy.id),
    ])
    await session.flush()

    async def _add_inventory(
        svc: Service, slug: str, name: str, price: float
    ) -> StoreInventory:
        category = Category(service_id=svc.id, slug=f"{slug}-cat")
        session.add(category)
        await session.flush()
        session.add(CategoryTranslation(
            category_id=category.id, language_code="en", name=f"{name}-cat",
        ))
        subcat = Subcategory(category_id=category.id, slug=f"{slug}-sub")
        session.add(subcat)
        await session.flush()
        session.add(SubcategoryTranslation(
            subcategory_id=subcat.id, language_code="en", name=f"{name}-sub",
        ))
        product = MasterProduct(subcategory_id=subcat.id, slug=slug, base_price=price)
        session.add(product)
        await session.flush()
        session.add(MasterProductTranslation(
            master_product_id=product.id, language_code="en", name=name, description=name,
        ))
        await session.flush()
        inv = StoreInventory(
            store_id=store.id, product_id=product.id, price=price, stock=10, is_available=True,
        )
        session.add(inv)
        await session.flush()
        return inv

    g_inv = await _add_inventory(grocery, "ricesvc", "Rice", 50.0)
    p_inv = await _add_inventory(pharmacy, "paracsvc", "Paracetamol", 20.0)

    # Pre-populate both sub-baskets for the customer.
    g_cart = Cart(
        customer_profile_id=customer.id, store_id=store.id, service_id=grocery.id,
    )
    p_cart = Cart(
        customer_profile_id=customer.id, store_id=store.id, service_id=pharmacy.id,
    )
    session.add_all([g_cart, p_cart])
    await session.flush()
    session.add_all([
        CartItem(cart_id=g_cart.id, inventory_id=g_inv.id, quantity=1),
        CartItem(cart_id=p_cart.id, inventory_id=p_inv.id, quantity=1),
    ])
    await session.commit()

    yield {
        "customer_address_id": (
            await session.exec(select(CustomerAddress.id).where(
                CustomerAddress.customer_profile_id == customer.id
            ))
        ).first(),
        "store_id": store.id,
        "grocery_id": grocery.id,
        "pharmacy_id": pharmacy.id,
        "grocery_inv_id": g_inv.id,
        "pharmacy_inv_id": p_inv.id,
        "seller_id": seller.id,
    }


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 2: Test `place_grocery_order_leaves_pharmacy_basket`**

```python
async def test_place_grocery_order_leaves_pharmacy_basket(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    resp = await client.post(
        "/api/v1/orders",
        json={
            "customer_address_id": seed["customer_address_id"],
            "store_id": seed["store_id"],
            "service_id": seed["grocery_id"],
            "payment_method": "upi",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["service_id"] == seed["grocery_id"]
    assert body["service_name"] == "Grocery"

    remaining = (await session.exec(select(Cart))).all()
    assert [c.service_id for c in remaining] == [seed["pharmacy_id"]]
```

- [ ] **Step 3: Test `seller_revoked_service_rejects_with_409`**

```python
async def test_seller_revoked_service_rejects_with_409(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    # Revoke pharmacy from the seller after the customer has built the basket.
    spsv = (await session.exec(
        select(SellerProfileService).where(
            SellerProfileService.seller_profile_id == seed["seller_id"],
            SellerProfileService.service_id == seed["pharmacy_id"],
        )
    )).first()
    assert spsv is not None
    await session.delete(spsv)
    await session.commit()

    resp = await client.post(
        "/api/v1/orders",
        json={
            "customer_address_id": seed["customer_address_id"],
            "store_id": seed["store_id"],
            "service_id": seed["pharmacy_id"],
            "payment_method": "upi",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["detail"] == "service_unavailable"

    # Basket is untouched.
    remaining = (await session.exec(select(Cart))).all()
    assert len(remaining) == 2
```

- [ ] **Step 4: Test `catalog_drift_after_add_to_cart_raises_409_service_mismatch`**

```python
async def test_catalog_drift_after_add_to_cart_raises_409(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    # Admin moves the grocery product into the pharmacy service after the
    # customer added it. We simulate by reparenting the category on the fly.
    from app.models.catalog import Category, Subcategory

    subcat = (await session.exec(
        select(Subcategory).join(  # type: ignore[arg-type]
            MasterProduct, MasterProduct.subcategory_id == Subcategory.id,
        ).join(  # type: ignore[arg-type]
            StoreInventory, StoreInventory.product_id == MasterProduct.id,
        ).where(StoreInventory.id == seed["grocery_inv_id"])
    )).first()
    assert subcat is not None
    category = (await session.exec(
        select(Category).where(Category.id == subcat.category_id)
    )).first()
    assert category is not None
    category.service_id = seed["pharmacy_id"]
    await session.commit()

    resp = await client.post(
        "/api/v1/orders",
        json={
            "customer_address_id": seed["customer_address_id"],
            "store_id": seed["store_id"],
            "service_id": seed["grocery_id"],
            "payment_method": "upi",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["detail"] == "service_mismatch"
```

- [ ] **Step 5: Test `list_orders_filter_by_service_id`**

```python
async def test_list_orders_filter_by_service_id(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    for svc_id in (seed["grocery_id"], seed["pharmacy_id"]):
        resp = await client.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_id"],
                "service_id": svc_id,
                "payment_method": "upi",
            },
        )
        assert resp.status_code == 201, resp.text

    grocery_only = (await client.get(
        f"/api/v1/orders?service_id={seed['grocery_id']}"
    )).json()["orders"]
    assert [o["service_id"] for o in grocery_only] == [seed["grocery_id"]]

    pharmacy_only = (await client.get(
        f"/api/v1/orders?service_id={seed['pharmacy_id']}"
    )).json()["orders"]
    assert [o["service_id"] for o in pharmacy_only] == [seed["pharmacy_id"]]
```

- [ ] **Step 6: Test `service_name_snapshot_slug_fallback`**

```python
async def test_service_name_snapshot_uses_slug_when_translation_missing(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    # Drop the English translation for grocery so the snapshot falls back to the slug.
    row = (await session.exec(
        select(ServiceTranslation).where(
            ServiceTranslation.service_id == seed["grocery_id"],
            ServiceTranslation.language_code == "en",
        )
    )).first()
    assert row is not None
    await session.delete(row)
    await session.commit()

    resp = await client.post(
        "/api/v1/orders",
        json={
            "customer_address_id": seed["customer_address_id"],
            "store_id": seed["store_id"],
            "service_id": seed["grocery_id"],
            "payment_method": "upi",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["service_name"] == "grocery"
```

- [ ] **Step 7: Run the new test file**

```bash
cd backend/app && uv run pytest tests/test_orders_per_service.py -v
```

Expected: all five tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/tests/test_orders_per_service.py
git commit -m "test(orders): per-service placement, drift, list filter, slug fallback"
```

---

## Task 15: Order emails surface the service name

**Files:**
- Modify: `backend/app/src/app/worker.py`

- [ ] **Step 1: Return service name from the email context loader**

Inside `_load_order_email_context`, after the `order = ...` line, add `service_name_snapshot` to the returned dict:

```python
                return {
                    "order_id": order.id,
                    "order_total": order.total,
                    "order_status": order.status.value,
                    "service_name": order.service_name_snapshot,
                    "store_name": store.name if store is not None else None,
                    "seller_email": seller_user.email if seller_user is not None else None,
                    "customer_email": customer_user.email if customer_user is not None else None,
                }
```

- [ ] **Step 2: Surface it in seller-placed emails**

Change `send_order_placed_seller_async`'s subject + body to:

```python
    subject = (
        f"New {ctx['service_name']} order received at "
        f"{ctx.get('store_name') or 'your store'}"
    )
    body = (
        f"You have a new {ctx['service_name']} order #{ctx['order_id']} for "
        f"{ctx.get('store_name') or 'your store'}.\n"
        f"Order total: {ctx['order_total']}.\n"
        f"Please prepare it for packing."
    )
```

- [ ] **Step 3: Surface it in customer-confirmed emails**

Change `send_order_confirmed_customer_async` to include the service in each summary line:

```python
        parts.append(
            f"Order #{ctx['order_id']} · {ctx['service_name']} "
            f"from {ctx.get('store_name') or 'a store'} - total {ctx['order_total']}"
        )
```

- [ ] **Step 4: Surface it in status-change emails**

Change `send_order_status_changed_async` subject + body to:

```python
    subject = (
        f"Order #{ctx['order_id']} · {ctx['service_name']} status: {new_status}"
    )
    body = (
        f"Order #{ctx['order_id']} ({ctx['service_name']}) from "
        f"{ctx.get('store_name') or 'a store'} is now '{new_status}'."
    )
```

- [ ] **Step 5: Type-check**

```bash
cd backend/app && uv run mypy src/app/worker.py
```

Expected: success.

- [ ] **Step 6: Update `tests/test_order_emails.py` expectations**

Open the file. Anywhere the test asserts subject/body strings, update the expected substring to include the service name (e.g., `assert "Grocery" in subject`). Re-run the test file:

```bash
cd backend/app && uv run pytest tests/test_order_emails.py -v
```

Expected: all passing.

- [ ] **Step 7: Commit**

```bash
git add backend/app/src/app/worker.py backend/app/tests/test_order_emails.py
git commit -m "feat(emails): include service name in order email subject and body"
```

---

## Task 16: Run the full backend suite

**Files:** none (validation only)

- [ ] **Step 1: Full backend test run**

```bash
cd backend/app && uv run pytest -v
```

Expected: every test passes. If `test_orders_serviceability.py` or `test_checkout.py` (if present) fails, update its payloads + assertions in the same way as Task 9 / Task 10 (thread `service_id`, expect new fields). Commit any such fix-ups under `test(orders): thread service_id through <file>` before proceeding.

- [ ] **Step 2: Lint + types**

```bash
cd backend/app && uv run ruff check . && uv run mypy .
```

Expected: both green. Fix any new violations introduced by this branch's edits inline.

- [ ] **Step 3: Commit any fix-ups generated above**

If Step 1 or Step 2 produced edits not yet committed, group them per file with conventional-commit subjects and commit. If everything was already green, skip this step.

---

## Task 17: Frontend type changes for Cart + Order

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Extend Cart and Order**

Replace the `Cart` interface block with:

```ts
/** A shopping cart sub-basket scoped to one (store, service) pair. */
export interface Cart {
  store_id: number;
  store_name: string;
  service_id: number;
  service_name: string;
  items: CartItem[];
}
```

Then add `service_id` + `service_name` to the `Order` interface, between `store_name` and `customer_name`:

```ts
export interface Order {
  id: number;
  store_id: number;
  store_name: string;
  service_id: number;
  service_name: string;
  customer_name?: string | null;
  status: OrderStatus;
  subtotal: number;
  delivery_fee: number;
  tax: number;
  total: number;
  placed_at: string;
  delivery_address_snapshot: string;
  items: OrderItem[];
  payment: OrderPayment;
  delivery: OrderDelivery;
}
```

- [ ] **Step 2: Lint**

```bash
cd frontend && npm run lint -- src/types/index.ts
```

Expected: no errors. Some downstream files will produce errors after this change — that is intended; the next tasks resolve them.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): Cart and Order gain service_id and service_name"
```

---

## Task 18: Guest cart in localStorage keys on `(storeId, serviceId)`

**Files:**
- Modify: `frontend/src/lib/localCart.ts`

- [ ] **Step 1: Replace the file body**

Overwrite `frontend/src/lib/localCart.ts` with:

```ts
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Khana Bazaar — Guest Cart (localStorage adapter).
 *
 * Each (store, service) pair has its own sub-basket. Carts persist across
 * page reloads. v2 storage key supersedes the legacy `kb_carts` key; the
 * legacy key is purged on first read so stale single-service carts cannot
 * accumulate indefinitely after the upgrade.
 */

import { Cart, CartItem } from "@/types";

const CARTS_KEY = "kb_carts_v2";
const LEGACY_CARTS_KEY = "kb_carts";
const SESSION_KEY = "kb_session_id";

let legacyPurged = false;

function purgeLegacyOnce(): void {
  if (legacyPurged || typeof window === "undefined") return;
  legacyPurged = true;
  localStorage.removeItem(LEGACY_CARTS_KEY);
}

/** Generate or retrieve a persistent guest session ID. */
export function getSessionId(): string {
  if (typeof window === "undefined") return "";
  let sid = localStorage.getItem(SESSION_KEY);
  if (!sid) {
    sid = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, sid);
  }
  return sid;
}

/** Read all sub-baskets from localStorage. */
export function getAllCarts(): Cart[] {
  if (typeof window === "undefined") return [];
  purgeLegacyOnce();
  try {
    const raw = localStorage.getItem(CARTS_KEY);
    return raw ? (JSON.parse(raw) as Cart[]) : [];
  } catch {
    return [];
  }
}

function saveCarts(carts: Cart[]): void {
  localStorage.setItem(CARTS_KEY, JSON.stringify(carts));
}

function find(
  carts: Cart[],
  storeId: number,
  serviceId: number,
): Cart | undefined {
  return carts.find(
    (c) => c.store_id === storeId && c.service_id === serviceId,
  );
}

/** Get a single sub-basket, or null. */
export function getCart(storeId: number, serviceId: number): Cart | null {
  return find(getAllCarts(), storeId, serviceId) ?? null;
}

/** Add an item to a sub-basket (or increment if already present). */
export function addToCart(
  storeId: number,
  storeName: string,
  serviceId: number,
  serviceName: string,
  item: CartItem,
): Cart[] {
  const carts = getAllCarts();
  let cart = find(carts, storeId, serviceId);

  if (!cart) {
    cart = {
      store_id: storeId,
      store_name: storeName,
      service_id: serviceId,
      service_name: serviceName,
      items: [],
    };
    carts.push(cart);
  }

  const existing = cart.items.find((i) => i.product_id === item.product_id);
  if (existing) {
    existing.quantity += item.quantity;
  } else {
    cart.items.push({ ...item });
  }

  saveCarts(carts);
  return carts;
}

/** Remove a specific product from a sub-basket. */
export function removeFromCart(
  storeId: number,
  serviceId: number,
  productId: number,
): Cart[] {
  const carts = getAllCarts();
  const cart = find(carts, storeId, serviceId);
  if (cart) {
    cart.items = cart.items.filter((i) => i.product_id !== productId);
    if (cart.items.length === 0) {
      const idx = carts.indexOf(cart);
      carts.splice(idx, 1);
    }
  }
  saveCarts(carts);
  return carts;
}

/** Update the quantity of a specific product in a sub-basket. */
export function updateQuantity(
  storeId: number,
  serviceId: number,
  productId: number,
  quantity: number,
): Cart[] {
  if (quantity <= 0) {
    return removeFromCart(storeId, serviceId, productId);
  }

  const carts = getAllCarts();
  const cart = find(carts, storeId, serviceId);
  if (cart) {
    const item = cart.items.find((i) => i.product_id === productId);
    if (item) item.quantity = quantity;
  }
  saveCarts(carts);
  return carts;
}

/** Clear a specific sub-basket. */
export function clearCart(storeId: number, serviceId: number): Cart[] {
  const carts = getAllCarts().filter(
    (c) => !(c.store_id === storeId && c.service_id === serviceId),
  );
  saveCarts(carts);
  return carts;
}

/** Clear all sub-baskets. */
export function clearAllCarts(): Cart[] {
  saveCarts([]);
  return [];
}
```

- [ ] **Step 2: Lint**

```bash
cd frontend && npm run lint -- src/lib/localCart.ts
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/localCart.ts
git commit -m "feat(localCart): key sub-baskets on (storeId, serviceId), bump to kb_carts_v2"
```

---

## Task 19: Remote cart layer carries `service_id`

**Files:**
- Modify: `frontend/src/lib/remoteCart.ts`

- [ ] **Step 1: Rewrite the file**

Overwrite `frontend/src/lib/remoteCart.ts` with:

```ts
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { del, get, patch, post } from "@/lib/api";
import type { Cart, CartItem } from "@/types";

interface RemoteCartItem {
  id: number;
  inventory_id: number;
  product_id: number;
  product_name: string;
  unit_price: number;
  quantity: number;
  line_total: number;
}

interface RemoteCart {
  store_id: number;
  store_name: string;
  service_id: number;
  service_name: string;
  items: RemoteCartItem[];
  subtotal: number;
}

interface RemoteCartListResponse {
  carts: RemoteCart[];
}

interface RemoteCartSyncResponse {
  carts: RemoteCart[];
  dropped: { inventory_id: number; reason: string }[];
}

function toCart(remote: RemoteCart): Cart {
  return {
    store_id: remote.store_id,
    store_name: remote.store_name,
    service_id: remote.service_id,
    service_name: remote.service_name,
    items: remote.items.map<CartItem>((item) => ({
      id: item.id,
      product_id: item.product_id,
      inventory_id: item.inventory_id,
      product_name: item.product_name,
      quantity: item.quantity,
      price: item.unit_price,
    })),
  };
}

export async function listCarts(token: string): Promise<Cart[]> {
  const data = await get<RemoteCartListResponse>("/api/v1/carts", token);
  return data.carts.map(toCart);
}

export async function addItem(
  token: string,
  storeId: number,
  serviceId: number,
  inventoryId: number,
  quantity: number,
): Promise<RemoteCartItem> {
  return post<RemoteCartItem>(
    "/api/v1/carts/items",
    {
      store_id: storeId,
      service_id: serviceId,
      inventory_id: inventoryId,
      quantity,
    },
    token,
  );
}

export async function updateItemQty(
  token: string,
  itemId: number,
  quantity: number,
): Promise<RemoteCartItem> {
  return patch<RemoteCartItem>(
    `/api/v1/carts/items/${itemId}`,
    { quantity },
    token,
  );
}

export async function removeItem(token: string, itemId: number): Promise<void> {
  await del<void>(`/api/v1/carts/items/${itemId}`, token);
}

export async function clearSubBasket(
  token: string,
  storeId: number,
  serviceId: number,
): Promise<void> {
  await del<void>(`/api/v1/carts/${storeId}/${serviceId}`, token);
}

export async function syncCarts(
  token: string,
  carts: {
    store_id: number;
    service_id: number;
    items: { inventory_id: number; quantity: number }[];
  }[],
): Promise<{
  carts: Cart[];
  dropped: { inventory_id: number; reason: string }[];
}> {
  const data = await post<RemoteCartSyncResponse>(
    "/api/v1/carts/sync",
    { carts },
    token,
  );
  return { carts: data.carts.map(toCart), dropped: data.dropped };
}
```

- [ ] **Step 2: Lint**

```bash
cd frontend && npm run lint -- src/lib/remoteCart.ts
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/remoteCart.ts
git commit -m "feat(remoteCart): clearSubBasket + sync payloads carry service_id"
```

---

## Task 20: `CartContext` mutator signatures pick up `serviceId`

**Files:**
- Modify: `frontend/src/lib/CartContext.tsx`

- [ ] **Step 1: Replace the file**

Overwrite `frontend/src/lib/CartContext.tsx` with:

```tsx
"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useAuth } from "@/lib/AuthContext";
import * as localCart from "@/lib/localCart";
import * as remoteCart from "@/lib/remoteCart";
import { getCartCount, getCartTotal, getGrandTotal } from "@/lib/cart";
import type { Cart, CartItem } from "@/types";

interface CartContextValue {
  carts: Cart[];
  cartCount: number;
  loading: boolean;
  addItem: (
    storeId: number,
    storeName: string,
    serviceId: number,
    serviceName: string,
    item: CartItem,
  ) => Promise<void>;
  removeItem: (
    storeId: number,
    serviceId: number,
    productId: number,
  ) => Promise<void>;
  updateQty: (
    storeId: number,
    serviceId: number,
    productId: number,
    qty: number,
  ) => Promise<void>;
  clearSubBasket: (storeId: number, serviceId: number) => Promise<void>;
  getTotal: (cart: Cart) => number;
  grandTotal: number;
  refresh: () => Promise<void>;
  lastSyncDropped: number;
  clearSyncDropped: () => void;
}

const CartContext = createContext<CartContextValue | null>(null);

function findRemoteItemId(
  carts: Cart[],
  storeId: number,
  serviceId: number,
  productId: number,
): number | undefined {
  const cart = carts.find(
    (c) => c.store_id === storeId && c.service_id === serviceId,
  );
  return cart?.items.find((i) => i.product_id === productId)?.id;
}

export function CartProvider({ children }: { children: React.ReactNode }) {
  const { dbUser, token, loading: authLoading } = useAuth();
  const [carts, setCarts] = useState<Cart[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [lastSyncDropped, setLastSyncDropped] = useState<number>(0);
  const lastSyncedUserId = useRef<number | null>(null);

  useEffect(() => {
    if (!dbUser) {
      lastSyncedUserId.current = null;
    }
  }, [dbUser]);

  const refreshLocal = useCallback(() => {
    setCarts(localCart.getAllCarts());
  }, []);

  const refreshRemote = useCallback(async () => {
    if (!token) return;
    const fresh = await remoteCart.listCarts(token);
    setCarts(fresh);
  }, [token]);

  const isCustomer = !!dbUser && dbUser.role === "customer" && !!token;

  const refresh = useCallback(async () => {
    if (isCustomer) {
      await refreshRemote();
    } else {
      refreshLocal();
    }
  }, [isCustomer, refreshRemote, refreshLocal]);

  useEffect(() => {
    if (authLoading) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      if (!dbUser || dbUser.role !== "customer" || !token) {
        if (!cancelled) {
          refreshLocal();
          setLoading(false);
        }
        return;
      }
      try {
        if (lastSyncedUserId.current !== dbUser.id) {
          const local = localCart.getAllCarts();
          if (local.length > 0) {
            const payload = local.map((c) => ({
              store_id: c.store_id,
              service_id: c.service_id,
              items: c.items
                .filter((i) => typeof i.inventory_id === "number")
                .map((i) => ({
                  inventory_id: i.inventory_id,
                  quantity: i.quantity,
                })),
            }));
            const result = await remoteCart.syncCarts(token, payload);
            if (!cancelled) {
              setCarts(result.carts);
              setLastSyncDropped(result.dropped.length);
            }
            localCart.clearAllCarts();
          } else {
            await refreshRemote();
          }
          lastSyncedUserId.current = dbUser.id;
        } else {
          await refreshRemote();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authLoading, dbUser, token, refreshLocal, refreshRemote]);

  const addItem = useCallback(
    async (
      storeId: number,
      storeName: string,
      serviceId: number,
      serviceName: string,
      item: CartItem,
    ) => {
      if (!isCustomer) {
        const updated = localCart.addToCart(
          storeId,
          storeName,
          serviceId,
          serviceName,
          item,
        );
        setCarts(updated);
        return;
      }
      const previous = carts;
      setCarts((prev) => {
        const next = prev.map((c) => ({ ...c, items: [...c.items] }));
        let cart = next.find(
          (c) => c.store_id === storeId && c.service_id === serviceId,
        );
        if (!cart) {
          cart = {
            store_id: storeId,
            store_name: storeName,
            service_id: serviceId,
            service_name: serviceName,
            items: [],
          };
          next.push(cart);
        }
        const existing = cart.items.find((i) => i.product_id === item.product_id);
        if (existing) {
          existing.quantity += item.quantity;
        } else {
          cart.items.push({ ...item });
        }
        return next;
      });
      try {
        await remoteCart.addItem(
          token!,
          storeId,
          serviceId,
          item.inventory_id,
          item.quantity,
        );
        await refreshRemote();
      } catch (err) {
        setCarts(previous);
        throw err;
      }
    },
    [carts, isCustomer, token, refreshRemote],
  );

  const removeItem = useCallback(
    async (storeId: number, serviceId: number, productId: number) => {
      if (!isCustomer) {
        setCarts(localCart.removeFromCart(storeId, serviceId, productId));
        return;
      }
      const previous = carts;
      const itemId = findRemoteItemId(carts, storeId, serviceId, productId);
      setCarts((prev) =>
        prev
          .map((c) =>
            c.store_id === storeId && c.service_id === serviceId
              ? { ...c, items: c.items.filter((i) => i.product_id !== productId) }
              : c,
          )
          .filter((c) => c.items.length > 0),
      );
      if (!itemId) return;
      try {
        await remoteCart.removeItem(token!, itemId);
        await refreshRemote();
      } catch (err) {
        setCarts(previous);
        throw err;
      }
    },
    [carts, isCustomer, token, refreshRemote],
  );

  const updateQty = useCallback(
    async (
      storeId: number,
      serviceId: number,
      productId: number,
      qty: number,
    ) => {
      if (qty <= 0) {
        await removeItem(storeId, serviceId, productId);
        return;
      }
      if (!isCustomer) {
        setCarts(localCart.updateQuantity(storeId, serviceId, productId, qty));
        return;
      }
      const previous = carts;
      const itemId = findRemoteItemId(carts, storeId, serviceId, productId);
      setCarts((prev) =>
        prev.map((c) =>
          c.store_id === storeId && c.service_id === serviceId
            ? {
                ...c,
                items: c.items.map((i) =>
                  i.product_id === productId ? { ...i, quantity: qty } : i,
                ),
              }
            : c,
        ),
      );
      if (!itemId) return;
      try {
        await remoteCart.updateItemQty(token!, itemId, qty);
        await refreshRemote();
      } catch (err) {
        setCarts(previous);
        throw err;
      }
    },
    [carts, isCustomer, token, refreshRemote, removeItem],
  );

  const clearSubBasket = useCallback(
    async (storeId: number, serviceId: number) => {
      if (!isCustomer) {
        setCarts(localCart.clearCart(storeId, serviceId));
        return;
      }
      const previous = carts;
      setCarts((prev) =>
        prev.filter(
          (c) => !(c.store_id === storeId && c.service_id === serviceId),
        ),
      );
      try {
        await remoteCart.clearSubBasket(token!, storeId, serviceId);
        await refreshRemote();
      } catch (err) {
        setCarts(previous);
        throw err;
      }
    },
    [carts, isCustomer, token, refreshRemote],
  );

  const cartCount = useMemo(() => getCartCount(carts), [carts]);
  const grandTotal = useMemo(() => getGrandTotal(carts), [carts]);

  const clearSyncDropped = useCallback(() => {
    setLastSyncDropped(0);
  }, []);

  const value: CartContextValue = {
    carts,
    cartCount,
    loading,
    addItem,
    removeItem,
    updateQty,
    clearSubBasket,
    getTotal: getCartTotal,
    grandTotal,
    refresh,
    lastSyncDropped,
    clearSyncDropped,
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used inside a CartProvider");
  return ctx;
}
```

- [ ] **Step 2: Lint**

```bash
cd frontend && npm run lint -- src/lib/CartContext.tsx
```

Expected: no errors in this file. Downstream call sites (`ProductCard`, cart page, checkout page, `CartRail`) will produce errors; those are fixed in the next tasks.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/CartContext.tsx
git commit -m "feat(cart-context): mutators key on (storeId, serviceId), rename to clearSubBasket"
```

---

## Task 21: `ProductCard` threads service identity into add/remove/update

**Files:**
- Modify: `frontend/src/components/ProductCard.tsx`

- [ ] **Step 1: Add the two props**

At the top of `ProductCard.tsx`, extend the `Props` interface and the function signature:

```tsx
interface Props {
  item: InventoryWithProduct;
  storeId: number;
  storeName: string;
  serviceId: number;
  serviceName: string;
}

export default function ProductCard({
  item, storeId, storeName, serviceId, serviceName,
}: Props) {
```

- [ ] **Step 2: Use the props in cart lookup + mutators**

Inside the function body, replace the cart-lookup and call sites:

```tsx
  const cart = carts.find(
    (c) => c.store_id === storeId && c.service_id === serviceId,
  );
  const cartItem = cart?.items.find((i) => i.product_id === product.id);
  const qty = cartItem?.quantity ?? 0;
```

Replace `handleAdd`:

```tsx
  const handleAdd = () => {
    addItem(storeId, storeName, serviceId, serviceName, {
      product_id: product.id,
      inventory_id: item.id,
      product_name: product.name,
      quantity: 1,
      price,
      image_url: product.image_url,
    });
  };
```

Replace the quantity-controls JSX so each call now passes `serviceId`:

```tsx
                <button
                  className={styles.qtyBtn}
                  onClick={() =>
                    qty <= 1
                      ? removeItem(storeId, serviceId, product.id)
                      : updateQty(storeId, serviceId, product.id, qty - 1)
                  }
                  aria-label={t("decreaseQty")}
                >
                  −
                </button>
                <span className={styles.qtyValue}>{qty}</span>
                <button
                  className={styles.qtyBtn}
                  onClick={() =>
                    updateQty(storeId, serviceId, product.id, qty + 1)
                  }
                  disabled={qty >= stock}
                  aria-label={t("increaseQty")}
                >
                  +
                </button>
```

- [ ] **Step 3: Lint**

```bash
cd frontend && npm run lint -- src/components/ProductCard.tsx
```

Expected: no errors in this file.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ProductCard.tsx
git commit -m "feat(ProductCard): thread serviceId/serviceName into cart calls"
```

---

## Task 22: Store-detail page passes active service into each `<ProductCard>`

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx`

- [ ] **Step 1: Thread the active service into `CategorySection`**

In `frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx`, change the `CategorySectionProps` interface to include the service identity, the `CategorySection` props, and the `<ProductCard>` invocations:

```tsx
interface CategorySectionProps {
  node: CategoryNode;
  store: Store;
  service: Service;
  activeSubcategoryId: number | null;
  onSubcategoryChange: (categoryId: number, subcategoryId: number | null) => void;
}
```

In the body, replace the `<ProductCard ... />` call with:

```tsx
            <ProductCard
              key={item.id}
              item={item}
              storeId={store.id}
              storeName={store.name}
              serviceId={service.id}
              serviceName={service.name}
            />
```

- [ ] **Step 2: Pass `service` into each `CategorySection`**

Inside the main page's `activeServiceNode &&` block, propagate it:

```tsx
              {activeServiceNode && (
                <div>
                  {activeServiceNode.categories.map((cn) => (
                    <CategorySection
                      key={cn.category.id}
                      node={cn}
                      store={store}
                      service={activeServiceNode.service}
                      activeSubcategoryId={subcategoryFilters[cn.category.id] ?? null}
                      onSubcategoryChange={handleSubcategoryChange}
                    />
                  ))}
                </div>
              )}
```

- [ ] **Step 3: Lint**

```bash
cd frontend && npm run lint -- 'src/app/(customer)/[locale]/stores/[id]/page.tsx'
```

Expected: no errors in this file.

- [ ] **Step 4: Commit**

```bash
git add 'frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx'
git commit -m "feat(store-detail): pass active service down to ProductCard"
```

---

## Task 23: Cart page groups by store then by service

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/cart/page.tsx`

- [ ] **Step 1: Re-shape the cart page render**

Overwrite `frontend/src/app/(customer)/[locale]/cart/page.tsx` with:

```tsx
"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { apiErrorKey } from "@/lib/errors";
import type { Cart } from "@/types";
import styles from "./page.module.css";

interface StoreGroup {
  store_id: number;
  store_name: string;
  subBaskets: Cart[];
}

function groupByStore(carts: Cart[]): StoreGroup[] {
  const byId = new Map<number, StoreGroup>();
  for (const c of carts) {
    let g = byId.get(c.store_id);
    if (!g) {
      g = { store_id: c.store_id, store_name: c.store_name, subBaskets: [] };
      byId.set(c.store_id, g);
    }
    g.subBaskets.push(c);
  }
  for (const g of byId.values()) {
    g.subBaskets.sort((a, b) => a.service_id - b.service_id);
  }
  return [...byId.values()];
}

export default function CartPage() {
  const t = useTranslations("Cart");
  const tErr = useTranslations("Errors");
  const { carts, removeItem, updateQty, clearSubBasket, getTotal } = useCart();
  const { dbUser } = useAuth();
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const storeGroups = useMemo(() => groupByStore(carts), [carts]);

  const handleClear = async (storeId: number, serviceId: number) => {
    setErrorMsg(null);
    try {
      await clearSubBasket(storeId, serviceId);
    } catch (err) {
      const key = apiErrorKey(err);
      if (key) {
        setErrorMsg(tErr(key.replace(/^Errors\./, "")));
      } else {
        const detail =
          (err as { detail?: string })?.detail ??
          (err instanceof Error ? err.message : null);
        setErrorMsg(detail ?? t("errClear"));
      }
    }
  };

  const handleRemove = async (
    storeId: number,
    serviceId: number,
    productId: number,
  ) => {
    setErrorMsg(null);
    try {
      await removeItem(storeId, serviceId, productId);
    } catch (err) {
      const key = apiErrorKey(err);
      if (key) {
        setErrorMsg(tErr(key.replace(/^Errors\./, "")));
      } else {
        const detail =
          (err as { detail?: string })?.detail ??
          (err instanceof Error ? err.message : null);
        setErrorMsg(detail ?? t("errRemove"));
      }
    }
  };

  const handleUpdateQty = async (
    storeId: number,
    serviceId: number,
    productId: number,
    qty: number,
  ) => {
    setErrorMsg(null);
    try {
      await updateQty(storeId, serviceId, productId, qty);
    } catch (err) {
      const key = apiErrorKey(err);
      if (key) {
        setErrorMsg(tErr(key.replace(/^Errors\./, "")));
      } else {
        const detail =
          (err as { detail?: string })?.detail ??
          (err instanceof Error ? err.message : null);
        setErrorMsg(detail ?? t("errUpdateQty"));
      }
    }
  };

  if (carts.length === 0) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>🛒</div>
            <h1 className={styles.emptyTitle}>{t("emptyTitle")}</h1>
            <p className={styles.emptyText}>{t("emptyBody")}</p>
            <Link href="/stores" className="btn btn-primary" id="empty-cart-shop">
              {t("startShopping")}
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const isCustomer = dbUser?.role === "customer";

  const renderCheckoutCta = (
    storeId: number,
    serviceId: number,
    serviceName: string,
    subtotal: number,
  ) => {
    if (!dbUser) {
      return (
        <Link
          href={`/login?next=/checkout/${storeId}/${serviceId}`}
          className={styles.checkoutBtn}
        >
          {t("loginToCheckout")}
        </Link>
      );
    }
    if (!isCustomer) {
      return (
        <span className={styles.checkoutBtn} aria-disabled>
          {t("customerLoginRequired")}
        </span>
      );
    }
    return (
      <Link
        href={`/checkout/${storeId}/${serviceId}`}
        className={styles.checkoutBtn}
      >
        {t("checkoutCta", { subtotal, service: serviceName })}
      </Link>
    );
  };

  const totalItems = carts.reduce(
    (sum, c) => sum + c.items.reduce((s, i) => s + i.quantity, 0),
    0,
  );

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        <div className={styles.header}>
          <h1 className={styles.title}>
            {t("yourLabel")}{" "}
            <span className={styles.titleAccent}>{t("cartLabel")}</span>
          </h1>
          <p className={styles.subtitle}>
            {t("summary", { stores: storeGroups.length, items: totalItems })}
          </p>
        </div>

        {errorMsg ? (
          <div role="alert" className={styles.errorBanner}>
            {errorMsg}
          </div>
        ) : null}

        {storeGroups.map((group) => (
          <div key={group.store_id} className={styles.storeGroup}>
            <div className={styles.storeGroupHeader}>
              <div className={styles.storeGroupTitle}>
                🏪{" "}
                <Link
                  href={`/stores/${group.store_id}`}
                  className={styles.storeGroupLink}
                >
                  {group.store_name}
                </Link>
              </div>
            </div>

            {group.subBaskets.map((cart) => {
              const subtotal = getTotal(cart);
              const showServiceHeader = group.subBaskets.length > 1;
              return (
                <div key={cart.service_id} className={styles.serviceSection}>
                  {showServiceHeader && (
                    <div className={styles.serviceHeader}>
                      <span className={styles.serviceName}>
                        {cart.service_name}
                      </span>
                      <button
                        className={styles.clearBtn}
                        onClick={() =>
                          handleClear(cart.store_id, cart.service_id)
                        }
                      >
                        {t("clearAll")}
                      </button>
                    </div>
                  )}
                  {!showServiceHeader && (
                    <div className={styles.serviceHeader}>
                      <button
                        className={styles.clearBtn}
                        onClick={() =>
                          handleClear(cart.store_id, cart.service_id)
                        }
                      >
                        {t("clearAll")}
                      </button>
                    </div>
                  )}

                  {cart.items.map((item) => (
                    <div key={item.product_id} className={styles.cartItem}>
                      <div className={styles.itemEmoji}>📦</div>

                      <div className={styles.itemInfo}>
                        <div className={styles.itemName}>{item.product_name}</div>
                        <div className={styles.itemPrice}>
                          {t("priceEach", { price: item.price })}
                        </div>
                      </div>

                      <div className={styles.qtyControls}>
                        <button
                          className={styles.qtyBtn}
                          onClick={() =>
                            item.quantity <= 1
                              ? handleRemove(
                                  cart.store_id,
                                  cart.service_id,
                                  item.product_id,
                                )
                              : handleUpdateQty(
                                  cart.store_id,
                                  cart.service_id,
                                  item.product_id,
                                  item.quantity - 1,
                                )
                          }
                        >
                          −
                        </button>
                        <span className={styles.qtyValue}>{item.quantity}</span>
                        <button
                          className={styles.qtyBtn}
                          onClick={() =>
                            handleUpdateQty(
                              cart.store_id,
                              cart.service_id,
                              item.product_id,
                              item.quantity + 1,
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
                        onClick={() =>
                          handleRemove(
                            cart.store_id,
                            cart.service_id,
                            item.product_id,
                          )
                        }
                        aria-label={t("removeAria", { name: item.product_name })}
                      >
                        ✕
                      </button>
                    </div>
                  ))}

                  <div className={styles.storeFooter}>
                    <span className={styles.storeSubtotalValue}>
                      {t("subtotal", { value: subtotal })}
                    </span>
                    {renderCheckoutCta(
                      cart.store_id,
                      cart.service_id,
                      cart.service_name,
                      subtotal,
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update the `checkoutCta` translation string**

Open `frontend/messages/en.json` (and any locale files that define `Cart.checkoutCta`). Change the existing message to include the service placeholder. Example for `en.json`:

```json
"checkoutCta": "Checkout {service} — ₹{subtotal}",
```

Update each other locale file in the same way (Hindi, Marathi, Gujarati, Punjabi). If a locale file is missing the key, copy the English placeholder so build-time `next-intl` validation passes.

- [ ] **Step 3: Add minimal CSS for the new service section**

Open `frontend/src/app/(customer)/[locale]/cart/page.module.css` and append:

```css
.serviceSection {
  margin-top: var(--space-3);
  border-top: 1px solid var(--shade-cool-light-2);
  padding-top: var(--space-3);
}

.serviceSection:first-of-type {
  border-top: none;
  padding-top: 0;
}

.serviceHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}

.serviceName {
  font-weight: 600;
  color: var(--text-primary);
}
```

- [ ] **Step 4: Lint**

```bash
cd frontend && npm run lint -- 'src/app/(customer)/[locale]/cart/page.tsx'
```

Expected: no errors in this file.

- [ ] **Step 5: Commit**

```bash
git add 'frontend/src/app/(customer)/[locale]/cart/page.tsx' \
        'frontend/src/app/(customer)/[locale]/cart/page.module.css' \
        frontend/messages
git commit -m "feat(cart-page): group by store then by service, per-sub-basket checkout"
```

---

## Task 24: Relocate checkout page to `/checkout/{storeId}/{serviceId}`

**Files:**
- Create: `frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.tsx`
- Create: `frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.module.css`
- Modify (DELETE): `frontend/src/app/(customer)/[locale]/checkout/[storeId]/page.tsx`
- Modify (DELETE): `frontend/src/app/(customer)/[locale]/checkout/[storeId]/page.module.css`

- [ ] **Step 1: Copy the existing CSS module**

```bash
cp 'frontend/src/app/(customer)/[locale]/checkout/[storeId]/page.module.css' \
   'frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.module.css'
```

- [ ] **Step 2: Write the new page**

Create `frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.tsx` with:

```tsx
"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { apiErrorKey } from "@/lib/errors";
import { get } from "@/lib/api";
import { placeOrder } from "@/lib/orders";
import AddressPicker from "@/components/orders/AddressPicker";
import { DeliveryRouteMap } from "@/components/orders/DeliveryRouteMap";
import PaymentMethodPicker from "@/components/orders/PaymentMethodPicker";
import type { PaymentMethod, Store } from "@/types";
import styles from "./page.module.css";

export default function CheckoutPage() {
  const t = useTranslations("Checkout");
  const tErr = useTranslations("Errors");
  const params = useParams<{ storeId: string; serviceId: string }>();
  const storeId = Number(params.storeId);
  const serviceId = Number(params.serviceId);
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();
  const { carts, loading: cartLoading, refresh, getTotal } = useCart();

  const [addressId, setAddressId] = useState<number | null>(null);
  const [selectedAddress, setSelectedAddress] = useState<{
    id: number;
    latitude: number | null;
    longitude: number | null;
    serviceable: boolean;
  } | null>(null);
  const [storeDetails, setStoreDetails] = useState<Store | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("upi");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!storeId || Number.isNaN(storeId)) return;
    get<Store>(`/api/v1/stores/${storeId}`)
      .then(setStoreDetails)
      .catch(() => setStoreDetails(null));
  }, [storeId]);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId, serviceId]);

  const cart = useMemo(
    () =>
      carts.find(
        (c) => c.store_id === storeId && c.service_id === serviceId,
      ),
    [carts, storeId, serviceId],
  );

  const isCustomer = dbUser?.role === "customer";

  useEffect(() => {
    if (!authLoading && !cartLoading && isCustomer && !cart) {
      router.replace("/cart");
    }
  }, [authLoading, cartLoading, isCustomer, cart, router]);

  if (authLoading || cartLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <p className={styles.loadingText}>{t("loading")}</p>
        </div>
      </div>
    );
  }

  if (!dbUser) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <p className={styles.loadingText}>
            {t.rich("loginPrompt", {
              login: () => (
                <Link href={`/login?next=/checkout/${storeId}/${serviceId}`}>
                  {t("loginLink")}
                </Link>
              ),
            })}
          </p>
        </div>
      </div>
    );
  }

  if (!isCustomer) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <p className={styles.loadingText}>{t("customerLoginRequired")}</p>
        </div>
      </div>
    );
  }

  if (!cart) {
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
        serviceId,
        paymentMethod,
      });
      router.push("/account/orders?placed=1");
    } catch (e) {
      const key = apiErrorKey(e);
      if (key) {
        setError(tErr(key.replace(/^Errors\./, "")));
      } else {
        const detail = (e as { detail?: unknown })?.detail;
        if (typeof detail === "string") {
          setError(detail);
        } else if (detail && typeof detail === "object" && "detail" in detail) {
          setError(String((detail as { detail: unknown }).detail));
        } else {
          setError(t("errPlaceOrder"));
        }
      }
      if (
        key === "service_unavailable" ||
        key === "service_mismatch"
      ) {
        router.push("/cart");
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
            {t("backToCart")}
          </Link>
          <h1 className={styles.title}>
            {t("title", { store: cart.store_name })} · {cart.service_name}
          </h1>
        </div>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{t("items")}</h2>
          <ul className={styles.itemList}>
            {cart.items.map((item) => (
              <li key={item.product_id} className={styles.itemRow}>
                <span className={styles.itemName}>{item.product_name}</span>
                <span className={styles.itemQty}>× {item.quantity}</span>
                <span className={styles.itemPrice}>
                  ₹{item.price * item.quantity}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{t("deliveryAddress")}</h2>
          <AddressPicker
            value={addressId}
            onChange={setAddressId}
            storeId={storeId}
            onSelectedAddress={setSelectedAddress}
          />
          {selectedAddress?.serviceable &&
            selectedAddress.latitude != null &&
            selectedAddress.longitude != null &&
            storeDetails?.address.latitude != null &&
            storeDetails?.address.longitude != null && (
              <div className={styles.routeMap}>
                <DeliveryRouteMap
                  store={{
                    lat: storeDetails.address.latitude,
                    lng: storeDetails.address.longitude,
                    label: storeDetails.name,
                  }}
                  customer={{
                    lat: selectedAddress.latitude,
                    lng: selectedAddress.longitude,
                    label: "Your address",
                  }}
                />
              </div>
            )}
        </section>

        <section className={styles.section}>
          <PaymentMethodPicker
            value={paymentMethod}
            onChange={setPaymentMethod}
          />
        </section>

        <section className={styles.summary}>
          <div className={styles.summaryRow}>
            <span>{t("subtotal")}</span>
            <span>₹{subtotal}</span>
          </div>
          <div className={styles.summaryRow}>
            <span>{t("deliveryFee")}</span>
            <span>₹{deliveryFee}</span>
          </div>
          <div className={styles.summaryRow}>
            <span>{t("tax")}</span>
            <span>₹{tax}</span>
          </div>
          <div className={`${styles.summaryRow} ${styles.summaryTotal}`}>
            <span>{t("total")}</span>
            <span>₹{total}</span>
          </div>
        </section>

        {error && <div className={styles.error}>{error}</div>}

        <button
          className={styles.placeBtn}
          onClick={onPlaceOrder}
          disabled={submitting || addressId === null}
        >
          {submitting ? t("placing") : t("placeOrder", { total })}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Update `placeOrder` signature in `lib/orders.ts`**

```ts
export interface PlaceOrderArgs {
  customerAddressId: number;
  storeId: number;
  serviceId: number;
  paymentMethod: PaymentMethod;
}

export async function placeOrder(
  token: string,
  args: PlaceOrderArgs,
): Promise<Order> {
  return post<Order>(
    "/api/v1/orders",
    {
      customer_address_id: args.customerAddressId,
      store_id: args.storeId,
      service_id: args.serviceId,
      payment_method: args.paymentMethod,
    },
    token,
  );
}
```

- [ ] **Step 4: Delete the old per-store checkout page**

```bash
git rm 'frontend/src/app/(customer)/[locale]/checkout/[storeId]/page.tsx' \
       'frontend/src/app/(customer)/[locale]/checkout/[storeId]/page.module.css'
```

- [ ] **Step 5: Lint**

```bash
cd frontend && npm run lint
```

Expected: no errors. If `apiErrorKey` does not return the `service_unavailable` or `service_mismatch` keys, ensure the corresponding entries exist in `frontend/src/lib/errors.ts` and the locale files — add them if missing.

- [ ] **Step 6: Commit**

```bash
git add 'frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.tsx' \
        'frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.module.css' \
        frontend/src/lib/orders.ts \
        frontend/src/lib/errors.ts 2>/dev/null || true
git commit -m "feat(checkout): relocate to /checkout/{storeId}/{serviceId} with service_id payload"
```

The `|| true` keeps the commit running even if `errors.ts` did not need a change.

---

## Task 25: `CartRail` routes the checkout button per-sub-basket

**Files:**
- Modify: `frontend/src/components/CartRail.tsx`

- [ ] **Step 1: Accept optional serviceId**

Update the `Props` interface and the lookup + handler:

```tsx
interface Props {
  storeId?: number;
  serviceId?: number;
}

export default function CartRail({ storeId, serviceId }: Props) {
  const { carts } = useCart();
  const { dbUser } = useAuth();
  const router = useRouter();

  const role = dbUser?.role;
  if (role && role !== "customer") return null;

  const cart =
    storeId != null && serviceId != null
      ? carts.find(
          (c) => c.store_id === storeId && c.service_id === serviceId,
        )
      : null;

  // ...

  const onCheckout = () => {
    if (storeId != null && serviceId != null) {
      router.push(`/checkout/${storeId}/${serviceId}`);
    } else {
      router.push("/cart");
    }
  };
```

- [ ] **Step 2: Pass active service into `<CartRail>` from the store-detail page**

In `frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx`, replace the existing `<CartRail storeId={store.id} />` line with:

```tsx
        <CartRail
          storeId={store.id}
          serviceId={activeServiceNode?.service.id}
        />
```

- [ ] **Step 3: Lint**

```bash
cd frontend && npm run lint -- src/components/CartRail.tsx 'src/app/(customer)/[locale]/stores/[id]/page.tsx'
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/CartRail.tsx 'frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx'
git commit -m "feat(CartRail): scope rail to active service, route to per-service checkout"
```

---

## Task 26: Order list + detail UI surfaces the service chip

**Files:**
- Modify: `frontend/src/components/orders/OrderCard.tsx` (path may vary — locate via the imports in `account/orders/page.tsx`)
- Modify: any header in `account/orders/[id]/page.tsx` that prints the store name

- [ ] **Step 1: Locate the rendering sites**

```bash
grep -RIn "store_name" frontend/src/app/\(customer\)/[locale]/account/orders/ frontend/src/components/orders/
```

Note each call site that already prints `store_name`. The rule: wherever `store_name` is rendered alone in a header position, also render `service_name` next to it as a chip / dot-separated suffix (e.g. `Store A · Grocery`).

- [ ] **Step 2: Update each card / header**

For every matched site, render:

```tsx
<>
  {order.store_name} <span className={styles.serviceChip}>· {order.service_name}</span>
</>
```

If `styles.serviceChip` does not exist in that component's CSS module, add:

```css
.serviceChip {
  color: var(--text-secondary);
  font-weight: 400;
}
```

- [ ] **Step 3: Lint**

```bash
cd frontend && npm run lint
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/orders/ 'frontend/src/app/(customer)/[locale]/account/orders/'
git commit -m "feat(orders-ui): show service chip next to store name on order cards and detail"
```

---

## Task 27: Manual frontend smoke

**Files:** none (manual verification only)

This task is a checklist of in-browser sanity checks — record results in the PR description, not a file.

- [ ] **Step 1: Start the stack**

```bash
docker-compose up -d
cd backend/app && uv run alembic upgrade head
cd backend/app && uv run uvicorn app.main:app --reload &
cd frontend && npm run dev
```

Open `http://localhost:3000`.

- [ ] **Step 2: Verify guest auto-split**

Browse to a store that offers ≥2 services (e.g. Grocery + Pharmacy). Add one Grocery product and one Pharmacy product. Open `/cart` and confirm:
- One store card.
- Two service sections inside the card with the correct service name and item count.
- Two "Checkout {service}" buttons.

- [ ] **Step 3: Verify per-service checkout for an authenticated customer**

Log in as a customer. Repeat Step 2 (the previous local-cart auto-syncs on login). From `/cart`, click "Checkout Grocery". Confirm the route is `/checkout/{storeId}/{groceryServiceId}` and the order summary lists only Grocery items. Place the order. Confirm the page bounces to `/account/orders?placed=1` and the new order's chip reads `… · Grocery`. Re-open `/cart`; only the Pharmacy section for that store remains.

- [ ] **Step 4: Verify single-service store**

Browse to a store that offers exactly one service. Add an item. On `/cart` the service section header should be suppressed but the per-service checkout button still reads "Checkout {service}".

- [ ] **Step 5: Verify v1→v2 cart purge**

In DevTools → Application → localStorage, manually insert a legacy `kb_carts` value (`[]` is enough). Reload the page; the legacy key should be absent on next read of localStorage.

- [ ] **Step 6: Order email check (dev console provider)**

Tail the backend log while placing an order. The Celery email log line should show a subject including the service name, e.g. `subject=Order #5 · Grocery status: pending`.

No commit at the end of this task — the verification log goes in the PR body when the branch is opened.

---

## Task 28: Docs

**Files:**
- Modify: `docs/flows.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update `docs/flows.md`**

Find the per-store-checkout section (around the line "per-store checkout" — first occurrence after the cart flow). Replace it with a per-store-per-service description:

- Carts are keyed `(customer_profile_id, store_id, service_id)` — auto-split on cross-service add, no modal.
- Each sub-basket checks out as its own Order. Sibling sub-baskets stay intact.
- Cart-add validates that the store's seller offers the service AND the inventory's product resolves to that service via `subcategory → category`.
- Checkout re-runs the seller-offers-service check and re-asserts the locked inventory's service against the payload's `service_id` to catch catalog drift.
- Order email subject/body now include the service name (snapshot at placement time, English with slug fallback).

- [ ] **Step 2: Update CLAUDE.md**

In `CLAUDE.md`, update the bullets under "Non-obvious patterns / gotchas":

- Replace any text describing Cart's unique key as `(customer, store)` with `(customer, store, service)`.
- Update the per-store-checkout bullet so it reads "per-store-per-service checkout": one Order per `(store, service)` sub-basket; cross-service add auto-splits.
- Add to the same bullet that catalog drift produces 409 `service_mismatch` and seller-revokes-service produces 409 `service_unavailable`, both at checkout (no auto cart purge).

Also update the `Order` schema table entry under "Key Files" if it mentions `service_id` would be missing.

- [ ] **Step 3: Commit**

```bash
git add docs/flows.md CLAUDE.md
git commit -m "docs: per-store-per-service checkout flow + CLAUDE.md updates"
```

---

## Task 29: Full final verification

**Files:** none (validation only)

- [ ] **Step 1: Backend green**

```bash
cd backend/app && uv run pytest -v && uv run ruff check . && uv run mypy .
```

Expected: 100% pass, 0 lint, 0 type errors.

- [ ] **Step 2: Frontend green**

```bash
cd frontend && npm run lint && npm run build
```

Expected: no lint errors; successful build.

- [ ] **Step 3: Manual checklist signed off**

Confirm every item in Task 27 was executed and the result captured in the PR draft.

- [ ] **Step 4: Open PR**

Open a PR against `main` per `CLAUDE.md` conventions (merge-commit, keep branch). Include in the body:
- A pointer to the design spec (`docs/superpowers/specs/2026-05-10-per-store-per-service-checkout-design.md`).
- The manual-verification checklist from Task 27 with results inline.
- An explicit "pre-launch full-nuke migration" call-out so reviewers know running this migration drops all transactional rows.

Do not push or open the PR until the user has approved the diff (per `CLAUDE.md`: "Wait for explicit user approval before opening PRs").
