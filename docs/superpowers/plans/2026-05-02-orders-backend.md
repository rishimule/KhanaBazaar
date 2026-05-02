# Orders — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the full backend for end-to-end orders: persisted customer cart with sync, COD checkout that fans out into per-store orders atomically, seller-driven status lifecycle, role-scoped read APIs, and Celery email notifications.

**Architecture:** Two new routers (`/carts`, `/orders`) sit on top of a thin service layer (`services/inventory.py`, `services/checkout.py`, `services/orders.py`, `services/order_emails.py`) that owns all business rules — RBAC checks, transitions, stock locks, side effects. API handlers parse, authorize, call the service, and serialize. One Alembic migration adds two composite indexes, an address snapshot column, and an `ON DELETE SET NULL` change. Three new Celery tasks send transactional email via the existing Resend pattern.

**Tech Stack:** FastAPI, SQLModel, SQLAlchemy, Alembic, Pydantic v2, Pytest + pytest-asyncio + httpx, Celery, Resend.

**Reference Spec:** `docs/superpowers/specs/2026-05-01-orders-design.md`

---

## File Structure

### New files

- `backend/app/migrations/versions/<rev>_orders_indexes_and_address_snapshot.py` — single migration covering all four schema changes.
- `backend/app/src/app/schemas/carts.py` — Pydantic request/response models for cart endpoints.
- `backend/app/src/app/schemas/orders.py` — Pydantic request/response models for order endpoints.
- `backend/app/src/app/services/inventory.py` — `decrement_stock`, `restock`, lock helper.
- `backend/app/src/app/services/checkout.py` — `place_orders_from_cart`.
- `backend/app/src/app/services/orders.py` — `transition_order_status`, `cancel_order`, legal-transition table.
- `backend/app/src/app/services/order_emails.py` — thin dispatcher wrappers around the Celery tasks (let API handlers stay framework-free).
- `backend/app/src/app/api/carts.py` — cart CRUD + sync router.
- `backend/app/src/app/api/orders.py` — order CRUD + transition + cancel router.
- `backend/app/tests/test_carts.py` — cart endpoint tests.
- `backend/app/tests/test_orders.py` — checkout, list, detail, transition, cancel tests.
- `backend/app/tests/test_order_emails.py` — email task tests with Resend mocked.

### Modified files

- `backend/app/src/app/api/__init__.py` — mount `carts.router` and `orders.router`.
- `backend/app/src/app/worker.py` — add three Celery tasks.

### Schema (already in place; do not redefine)

- `app.models.commerce.Cart`, `CartItem`, `Order`, `OrderItem`, `Payment`, `Delivery`, `OrderStatus`, `PaymentMethod`, `PaymentStatus`, `DeliveryStatus`.
- `app.models.store.StoreInventory` (fields: `id`, `store_id`, `product_id`, `price`, `stock`, `is_available`).
- `app.models.profile.CustomerAddress` (fields: `id`, `customer_profile_id`, `address_id`).
- `app.core.security.get_current_customer` (already exists, no changes).

---

## Task 1: Alembic migration

**Files:**
- Create: `backend/app/migrations/versions/<rev>_orders_indexes_and_address_snapshot.py`

- [ ] **Step 1: Generate revision**

Run from `backend/app/`:

```bash
uv run alembic revision -m "orders indexes and address snapshot"
```

Expected: prints path of new file with auto-generated revision hash. Open it.

- [ ] **Step 2: Replace generated file body**

Replace the generated `upgrade()` and `downgrade()` with:

```python
"""orders indexes and address snapshot

Revision ID: <auto>
Revises: <auto>
Create Date: <auto>
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic. (Keep the auto-generated values.)
revision: str = "<auto>"
down_revision: Union[str, None] = "<auto>"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_order_store_status",
        "order",
        ["store_id", "status"],
    )
    op.create_index(
        "ix_order_customer_status",
        "order",
        ["customer_profile_id", "status"],
    )
    op.add_column(
        "order",
        sa.Column(
            "delivery_address_snapshot",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
    op.alter_column("order", "delivery_address_snapshot", server_default=None)

    # Recreate orderitem.inventory_id FK with ON DELETE SET NULL so order
    # history survives if a seller removes an inventory row.
    op.alter_column("orderitem", "inventory_id", existing_type=sa.Integer(), nullable=True)
    with op.batch_alter_table("orderitem") as batch_op:
        batch_op.drop_constraint("orderitem_inventory_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "orderitem_inventory_id_fkey",
            "storeinventory",
            ["inventory_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("orderitem") as batch_op:
        batch_op.drop_constraint("orderitem_inventory_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "orderitem_inventory_id_fkey",
            "storeinventory",
            ["inventory_id"],
            ["id"],
        )
    op.alter_column("orderitem", "inventory_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("order", "delivery_address_snapshot")
    op.drop_index("ix_order_customer_status", table_name="order")
    op.drop_index("ix_order_store_status", table_name="order")
```

- [ ] **Step 3: Update SQLModel `Order` to include the snapshot column**

Modify `backend/app/src/app/models/commerce.py` — find the `Order` class and add this field after `total`:

```python
    delivery_address_snapshot: str = Field(default="", nullable=False)
```

Find the `OrderItem` class and change `inventory_id` to be nullable:

```python
    inventory_id: Optional[int] = Field(default=None, foreign_key="storeinventory.id")
```

(Keep the existing unique constraint definition. The `Optional` import is already present at top of file.)

- [ ] **Step 4: Apply migration**

```bash
uv run alembic upgrade head
```

Expected: prints `Running upgrade ... -> <new_rev>` and exits 0.

- [ ] **Step 5: Verify**

```bash
uv run python -c "
import asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        def check(sync_conn):
            insp = inspect(sync_conn)
            cols = [c['name'] for c in insp.get_columns('order')]
            assert 'delivery_address_snapshot' in cols, cols
            idxs = [i['name'] for i in insp.get_indexes('order')]
            assert 'ix_order_store_status' in idxs, idxs
            assert 'ix_order_customer_status' in idxs, idxs
            print('OK')
        await conn.run_sync(check)

asyncio.run(main())
"
```

Expected output: `OK`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/migrations/versions/ backend/app/src/app/models/commerce.py
git commit -m "feat(orders): add indexes, address snapshot, nullable inventory FK"
```

---

## Task 2: Cart Pydantic schemas

**Files:**
- Create: `backend/app/src/app/schemas/carts.py`

- [ ] **Step 1: Create schema file**

Create `backend/app/src/app/schemas/carts.py`:

```python
from typing import List, Optional

from pydantic import BaseModel, Field


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
    items: List[CartItemRead]
    subtotal: float


class CartListResponse(BaseModel):
    carts: List[CartRead]


class CartItemAdd(BaseModel):
    store_id: int
    inventory_id: int
    quantity: int = Field(gt=0)


class CartItemUpdate(BaseModel):
    quantity: int = Field(gt=0)


class CartSyncItem(BaseModel):
    inventory_id: int
    quantity: int = Field(gt=0)


class CartSyncCart(BaseModel):
    store_id: int
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

- [ ] **Step 2: Commit**

```bash
git add backend/app/src/app/schemas/carts.py
git commit -m "feat(carts): add cart pydantic schemas"
```

---

## Task 3: Cart helpers shared between endpoints

**Files:**
- Create: `backend/app/src/app/api/carts.py` (initial scaffolding only — endpoints land in later tasks)

- [ ] **Step 1: Create the file with helpers + empty router**

Create `backend/app/src/app/api/carts.py`:

```python
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_customer
from app.db.session import get_db_session
from app.models.base import User
from app.models.catalog import MasterProduct
from app.models.commerce import Cart, CartItem
from app.models.profile import CustomerProfile
from app.models.store import Store, StoreInventory
from app.schemas.carts import (
    CartItemAdd,
    CartItemRead,
    CartItemUpdate,
    CartListResponse,
    CartRead,
    CartSyncRequest,
    CartSyncResponse,
    DroppedSyncItem,
)

router = APIRouter()


async def _customer_profile_id(session: AsyncSession, user: User) -> int:
    assert user.id is not None
    result = await session.exec(
        select(CustomerProfile.id).where(CustomerProfile.user_id == user.id)
    )
    profile_id = result.first()
    if profile_id is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return profile_id


async def _get_or_create_cart(
    session: AsyncSession, customer_profile_id: int, store_id: int
) -> Cart:
    result = await session.exec(
        select(Cart).where(
            Cart.customer_profile_id == customer_profile_id,
            Cart.store_id == store_id,
        )
    )
    cart = result.first()
    if cart is None:
        # Validate store exists + active.
        store_result = await session.exec(select(Store).where(Store.id == store_id))
        store = store_result.first()
        if store is None or not store.is_active:
            raise HTTPException(status_code=404, detail="Store not found or inactive")
        cart = Cart(customer_profile_id=customer_profile_id, store_id=store_id)
        session.add(cart)
        await session.flush()
    return cart


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
    for item, inv, product, store in rows:
        by_cart.setdefault(item.cart_id, []).append((item, inv, product, store))

    out: list[CartRead] = []
    for cart in carts:
        assert cart.id is not None
        rows_for_cart = by_cart.get(cart.id, [])
        items = [
            CartItemRead(
                id=item.id,  # type: ignore[arg-type]
                inventory_id=inv.id,  # type: ignore[arg-type]
                product_id=product.id,  # type: ignore[arg-type]
                product_name=product.name,
                unit_price=inv.price,
                quantity=item.quantity,
                line_total=inv.price * item.quantity,
            )
            for item, inv, product, _ in rows_for_cart
        ]
        store_name = rows_for_cart[0][3].name if rows_for_cart else ""
        if not store_name:
            store_result = await session.exec(select(Store).where(Store.id == cart.store_id))
            store = store_result.first()
            store_name = store.name if store else ""
        out.append(
            CartRead(
                store_id=cart.store_id,
                store_name=store_name,
                items=items,
                subtotal=sum(i.line_total for i in items),
            )
        )
    return out
```

- [ ] **Step 2: Mount the router**

Modify `backend/app/src/app/api/__init__.py` — add the carts router (alphabetically with the others):

```python
from app.api import auth, carts, catalog, customers, meta, sellers, stores, tasks
```

And mount it (place after `customers`):

```python
api_router.include_router(carts.router, prefix="/carts", tags=["carts"])
```

- [ ] **Step 3: Verify the app boots**

```bash
uv run python -c "from app import app; print(sorted(r.path for r in app.routes))"
```

Expected: prints route list. No new cart paths yet (router has no endpoints), but the import must succeed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/api/carts.py backend/app/src/app/api/__init__.py
git commit -m "feat(carts): scaffold cart router and serializer helpers"
```

---

## Task 4: GET /carts endpoint + tests

**Files:**
- Modify: `backend/app/src/app/api/carts.py`
- Create: `backend/app/tests/test_carts.py`

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_carts.py`:

```python
from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Category, MasterProduct
from app.models.commerce import Cart, CartItem
from app.models.profile import CustomerProfile, SellerProfile, VerificationStatus
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

mock_customer = User(id=201, email="cart-customer@kb.com", role=UserRole.Customer, is_active=True)
mock_other_customer = User(id=202, email="cart-other@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=203, email="cart-seller@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[None, None]:
    for u in (mock_customer, mock_other_customer, mock_seller):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer_profile = CustomerProfile(user_id=mock_customer.id, first_name="Cust")
    other_profile = CustomerProfile(user_id=mock_other_customer.id, first_name="Other")
    session.add_all([customer_profile, other_profile])
    await session.flush()

    seller_addr = Address(**make_address(pincode="560001"))
    session.add(seller_addr)
    await session.flush()
    seller_profile = SellerProfile(
        user_id=mock_seller.id, first_name="Sel", phone="+919800000001",
        business_name="S", business_category="grocery",
        bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_addr.id,
    )
    session.add(seller_profile)
    await session.flush()

    store_addr = Address(**make_address(pincode="560002"))
    session.add(store_addr)
    await session.flush()
    store = Store(name="Test Store", seller_profile_id=seller_profile.id, address_id=store_addr.id)
    session.add(store)
    await session.flush()

    category = Category(name="Food", slug="food")
    session.add(category)
    await session.flush()
    product = MasterProduct(name="Apple", slug="apple", category_id=category.id)
    session.add(product)
    await session.flush()

    inv = StoreInventory(store_id=store.id, product_id=product.id, price=50.0, stock=10)
    session.add(inv)
    await session.flush()

    # Pre-existing cart row for the main customer for read tests.
    cart = Cart(customer_profile_id=customer_profile.id, store_id=store.id)
    session.add(cart)
    await session.flush()
    session.add(CartItem(cart_id=cart.id, inventory_id=inv.id, quantity=2))
    await session.commit()
    yield


@pytest.fixture
def override_as_customer() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_as_other_customer() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_other_customer
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_as_seller() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    yield
    app.dependency_overrides.pop(get_current_user, None)


async def test_guest_cannot_list_carts() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/carts")
    assert resp.status_code == 401


async def test_seller_cannot_list_carts(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/carts")
    assert resp.status_code == 403


async def test_customer_lists_their_carts(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/carts")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["carts"]) == 1
    cart = data["carts"][0]
    assert cart["store_name"] == "Test Store"
    assert cart["subtotal"] == 100.0
    assert cart["items"][0]["product_name"] == "Apple"
    assert cart["items"][0]["quantity"] == 2


async def test_other_customer_sees_empty_list(override_as_other_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/carts")
    assert resp.status_code == 200
    assert resp.json() == {"carts": []}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/test_carts.py -v
```

Expected: 4 tests, all collected; the auth tests likely 404 (no route), the success test 404. All must fail before we implement.

- [ ] **Step 3: Add the endpoint**

Append to `backend/app/src/app/api/carts.py`:

```python
@router.get("", response_model=CartListResponse)
@router.get("/", response_model=CartListResponse, include_in_schema=False)
async def list_carts(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> CartListResponse:
    profile_id = await _customer_profile_id(session, user)
    result = await session.exec(
        select(Cart).where(Cart.customer_profile_id == profile_id)
    )
    carts = list(result.all())
    return CartListResponse(carts=await _serialize_carts(session, carts))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_carts.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/carts.py backend/app/tests/test_carts.py
git commit -m "feat(carts): add GET /carts list endpoint"
```

---

## Task 5: POST /carts/items endpoint + tests

**Files:**
- Modify: `backend/app/src/app/api/carts.py`
- Modify: `backend/app/tests/test_carts.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/app/tests/test_carts.py`:

```python
async def test_add_item_to_new_cart(override_as_other_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Inventory id = 1 from seed (only one inventory row).
        resp = await ac.post("/api/v1/carts/items", json={
            "store_id": 1, "inventory_id": 1, "quantity": 3,
        })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["quantity"] == 3
    assert body["product_name"] == "Apple"


async def test_add_existing_item_increments_quantity(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/carts/items", json={
            "store_id": 1, "inventory_id": 1, "quantity": 5,
        })
    assert resp.status_code == 200, resp.text   # 200 = updated
    assert resp.json()["quantity"] == 7   # 2 (seeded) + 5


async def test_add_item_unknown_inventory(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/carts/items", json={
            "store_id": 1, "inventory_id": 9999, "quantity": 1,
        })
    assert resp.status_code == 404


async def test_add_item_inventory_not_in_store(override_as_customer: Any, session: AsyncSession) -> None:
    # Seed a second store + its inventory; passing store_id=1 + new inventory_id should 400.
    addr2 = Address(**make_address(pincode="560003"))
    session.add(addr2)
    await session.flush()
    seller2_profile_id = (await session.exec(
        __import__("sqlmodel").select(SellerProfile.id)
    )).first()
    store2 = Store(name="S2", seller_profile_id=seller2_profile_id, address_id=addr2.id)
    session.add(store2)
    await session.flush()
    inv2 = StoreInventory(store_id=store2.id, product_id=1, price=20.0, stock=5)
    session.add(inv2)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/carts/items", json={
            "store_id": 1, "inventory_id": inv2.id, "quantity": 1,
        })
    assert resp.status_code == 400
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_carts.py -v -k "add_item or increments_quantity"
```

Expected: 4 failed (route missing).

- [ ] **Step 3: Implement endpoint**

Append to `backend/app/src/app/api/carts.py`:

```python
from fastapi import status

@router.post("/items", response_model=CartItemRead)
async def add_cart_item(
    payload: CartItemAdd,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> Any:
    profile_id = await _customer_profile_id(session, user)

    inv_result = await session.exec(
        select(StoreInventory, MasterProduct)
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .where(StoreInventory.id == payload.inventory_id)
    )
    row = inv_result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Inventory not found")
    inv, product = row
    if inv.store_id != payload.store_id:
        raise HTTPException(status_code=400, detail="inventory_store_mismatch")
    if not inv.is_available:
        raise HTTPException(status_code=409, detail="item_unavailable")

    cart = await _get_or_create_cart(session, profile_id, payload.store_id)
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

    response = CartItemRead(
        id=item.id,  # type: ignore[arg-type]
        inventory_id=inv.id,  # type: ignore[arg-type]
        product_id=product.id,  # type: ignore[arg-type]
        product_name=product.name,
        unit_price=inv.price,
        quantity=item.quantity,
        line_total=inv.price * item.quantity,
    )
    from fastapi.responses import JSONResponse
    return JSONResponse(
        response.model_dump(),
        status_code=status.HTTP_200_OK if updated else status.HTTP_201_CREATED,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_carts.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/carts.py backend/app/tests/test_carts.py
git commit -m "feat(carts): add POST /carts/items"
```

---

## Task 6: PATCH and DELETE cart-item endpoints + tests

**Files:**
- Modify: `backend/app/src/app/api/carts.py`
- Modify: `backend/app/tests/test_carts.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/app/tests/test_carts.py`:

```python
async def test_update_item_quantity(override_as_customer: Any, session: AsyncSession) -> None:
    item_id = (await session.exec(__import__("sqlmodel").select(CartItem.id))).first()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(f"/api/v1/carts/items/{item_id}", json={"quantity": 4})
    assert resp.status_code == 200
    assert resp.json()["quantity"] == 4


async def test_update_item_other_customer_forbidden(override_as_other_customer: Any, session: AsyncSession) -> None:
    item_id = (await session.exec(__import__("sqlmodel").select(CartItem.id))).first()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(f"/api/v1/carts/items/{item_id}", json={"quantity": 4})
    assert resp.status_code == 403


async def test_delete_cart_item(override_as_customer: Any, session: AsyncSession) -> None:
    item_id = (await session.exec(__import__("sqlmodel").select(CartItem.id))).first()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete(f"/api/v1/carts/items/{item_id}")
    assert resp.status_code == 204
    # Cart row also gone (was the only item).
    await session.commit()
    remaining = (await session.exec(__import__("sqlmodel").select(Cart))).all()
    assert remaining == []


async def test_clear_store_cart(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/carts/1")
    assert resp.status_code == 204
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_carts.py -v -k "update_item or delete_cart or clear_store"
```

Expected: failures (routes missing).

- [ ] **Step 3: Implement endpoints**

Append to `backend/app/src/app/api/carts.py`:

```python
from fastapi import Response


async def _owned_cart_item(
    session: AsyncSession, profile_id: int, item_id: int
) -> tuple[CartItem, Cart]:
    result = await session.exec(
        select(CartItem, Cart)
        .join(Cart, Cart.id == CartItem.cart_id)  # type: ignore[arg-type]
        .where(CartItem.id == item_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Cart item not found")
    item, cart = row
    if cart.customer_profile_id != profile_id:
        raise HTTPException(status_code=403, detail="not_your_item")
    return item, cart


@router.patch("/items/{item_id}", response_model=CartItemRead)
async def update_cart_item(
    item_id: int,
    payload: CartItemUpdate,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> CartItemRead:
    profile_id = await _customer_profile_id(session, user)
    item, _ = await _owned_cart_item(session, profile_id, item_id)
    item.quantity = payload.quantity
    await session.commit()
    await session.refresh(item)

    inv_result = await session.exec(
        select(StoreInventory, MasterProduct)
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .where(StoreInventory.id == item.inventory_id)
    )
    inv, product = inv_result.first()  # type: ignore[misc]
    return CartItemRead(
        id=item.id,  # type: ignore[arg-type]
        inventory_id=inv.id,  # type: ignore[arg-type]
        product_id=product.id,  # type: ignore[arg-type]
        product_name=product.name,
        unit_price=inv.price,
        quantity=item.quantity,
        line_total=inv.price * item.quantity,
    )


@router.delete("/items/{item_id}", status_code=204)
async def delete_cart_item(
    item_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> Response:
    profile_id = await _customer_profile_id(session, user)
    item, cart = await _owned_cart_item(session, profile_id, item_id)
    await session.delete(item)
    await session.flush()

    # Drop the cart if empty.
    remaining = await session.exec(select(CartItem).where(CartItem.cart_id == cart.id))
    if remaining.first() is None:
        await session.delete(cart)
    await session.commit()
    return Response(status_code=204)


@router.delete("/{store_id}", status_code=204)
async def clear_store_cart(
    store_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> Response:
    profile_id = await _customer_profile_id(session, user)
    cart_result = await session.exec(
        select(Cart).where(
            Cart.customer_profile_id == profile_id, Cart.store_id == store_id
        )
    )
    cart = cart_result.first()
    if cart is not None:
        items_result = await session.exec(select(CartItem).where(CartItem.cart_id == cart.id))
        for item in items_result.all():
            await session.delete(item)
        await session.delete(cart)
        await session.commit()
    return Response(status_code=204)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_carts.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/carts.py backend/app/tests/test_carts.py
git commit -m "feat(carts): add PATCH/DELETE cart item + clear-store endpoints"
```

---

## Task 7: POST /carts/sync endpoint + tests

**Files:**
- Modify: `backend/app/src/app/api/carts.py`
- Modify: `backend/app/tests/test_carts.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/app/tests/test_carts.py`:

```python
async def test_sync_empty_payload(override_as_other_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/carts/sync", json={"carts": []})
    assert resp.status_code == 200
    assert resp.json() == {"carts": [], "dropped": []}


async def test_sync_merges_quantities(override_as_customer: Any) -> None:
    # Existing seed: store 1, inventory 1, qty 2.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/carts/sync", json={
            "carts": [{"store_id": 1, "items": [{"inventory_id": 1, "quantity": 5}]}]
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["dropped"] == []
    assert body["carts"][0]["items"][0]["quantity"] == 7   # 2 + 5


async def test_sync_drops_unknown_inventory(override_as_other_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/carts/sync", json={
            "carts": [{"store_id": 1, "items": [
                {"inventory_id": 1, "quantity": 1},
                {"inventory_id": 9999, "quantity": 2},
            ]}]
        })
    assert resp.status_code == 200
    body = resp.json()
    assert any(d["inventory_id"] == 9999 for d in body["dropped"])
    assert body["carts"][0]["items"][0]["inventory_id"] == 1
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_carts.py::test_sync_empty_payload tests/test_carts.py::test_sync_merges_quantities tests/test_carts.py::test_sync_drops_unknown_inventory -v
```

Expected: failures (route missing).

- [ ] **Step 3: Implement endpoint**

Append to `backend/app/src/app/api/carts.py`:

```python
@router.post("/sync", response_model=CartSyncResponse)
async def sync_carts(
    payload: CartSyncRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> CartSyncResponse:
    profile_id = await _customer_profile_id(session, user)
    dropped: list[DroppedSyncItem] = []

    for cart_payload in payload.carts:
        store_result = await session.exec(select(Store).where(Store.id == cart_payload.store_id))
        store = store_result.first()
        if store is None or not store.is_active:
            for it in cart_payload.items:
                dropped.append(DroppedSyncItem(inventory_id=it.inventory_id, reason="store_unavailable"))
            continue

        cart = await _get_or_create_cart(session, profile_id, cart_payload.store_id)

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

    # Return canonical cart state for the customer.
    result = await session.exec(
        select(Cart).where(Cart.customer_profile_id == profile_id)
    )
    carts = list(result.all())
    return CartSyncResponse(
        carts=await _serialize_carts(session, carts),
        dropped=dropped,
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_carts.py -v
```

Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/carts.py backend/app/tests/test_carts.py
git commit -m "feat(carts): add POST /carts/sync"
```

---

## Task 8: Order Pydantic schemas

**Files:**
- Create: `backend/app/src/app/schemas/orders.py`

- [ ] **Step 1: Create the file**

Create `backend/app/src/app/schemas/orders.py`:

```python
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from app.models.commerce import (
    DeliveryStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)


class OrderItemRead(BaseModel):
    id: int
    inventory_id: Optional[int]
    product_name_snapshot: str
    unit_price_snapshot: float
    quantity: int
    line_total: float


class PaymentRead(BaseModel):
    method: PaymentMethod
    status: PaymentStatus
    amount: float
    paid_at: Optional[datetime]


class DeliveryRead(BaseModel):
    status: DeliveryStatus
    packed_at: Optional[datetime]
    dispatched_at: Optional[datetime]
    delivered_at: Optional[datetime]


class OrderRead(BaseModel):
    id: int
    store_id: int
    store_name: str
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


class OrderListResponse(BaseModel):
    orders: List[OrderRead]


class PlaceOrderRequest(BaseModel):
    customer_address_id: int


class PlaceOrderResponse(BaseModel):
    orders: List[OrderRead]


class TransitionRequest(BaseModel):
    to: Literal["packed", "dispatched", "delivered"]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/src/app/schemas/orders.py
git commit -m "feat(orders): add order pydantic schemas"
```

---

## Task 9: Inventory service (decrement_stock, restock)

**Files:**
- Create: `backend/app/src/app/services/inventory.py`

- [ ] **Step 1: Create the service**

Create `backend/app/src/app/services/inventory.py`:

```python
from typing import Iterable

from sqlalchemy import update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.store import StoreInventory


async def lock_inventory_rows(
    session: AsyncSession, inventory_ids: Iterable[int]
) -> list[StoreInventory]:
    """Acquire per-row locks on inventory rows in deterministic order to avoid deadlocks."""
    ids = sorted(set(inventory_ids))
    if not ids:
        return []
    stmt = (
        select(StoreInventory)
        .where(StoreInventory.id.in_(ids))  # type: ignore[attr-defined]
        .with_for_update()
        .order_by(StoreInventory.id)  # type: ignore[arg-type]
    )
    result = await session.exec(stmt)
    return list(result.all())


async def decrement_stock(session: AsyncSession, inventory_id: int, quantity: int) -> None:
    await session.exec(  # type: ignore[call-overload]
        update(StoreInventory)
        .where(StoreInventory.id == inventory_id)
        .values(stock=StoreInventory.stock - quantity)
    )


async def restock(session: AsyncSession, inventory_id: int, quantity: int) -> None:
    await session.exec(  # type: ignore[call-overload]
        update(StoreInventory)
        .where(StoreInventory.id == inventory_id)
        .values(stock=StoreInventory.stock + quantity)
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/src/app/services/inventory.py
git commit -m "feat(orders): add inventory service helpers"
```

---

## Task 10: Checkout service

**Files:**
- Create: `backend/app/src/app/services/checkout.py`
- Create: `backend/app/src/app/utils/format_address.py` if not present (we just need a callable; check first)

- [ ] **Step 1: Check existing address formatter**

```bash
grep -rn "def format_address\|def address_to_str" backend/app/src/app/utils/ backend/app/src/app/schemas/ || true
```

If a formatter exists, import it. If not, the checkout service falls back to a local helper (Step 2 below includes one).

- [ ] **Step 2: Create the checkout service**

Create `backend/app/src/app/services/checkout.py`:

```python
from typing import List

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User
from app.models.catalog import MasterProduct
from app.models.commerce import (
    Cart,
    CartItem,
    Delivery,
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.profile import CustomerAddress, CustomerProfile
from app.models.store import Store, StoreInventory
from app.services.inventory import decrement_stock, lock_inventory_rows


def _format_address_snapshot(address: Address) -> str:
    parts = [
        address.line1,
        getattr(address, "line2", None),
        address.city,
        address.state,
        address.pincode,
    ]
    return ", ".join(p for p in parts if p)


async def _customer_profile(session: AsyncSession, user: User) -> CustomerProfile:
    assert user.id is not None
    result = await session.exec(
        select(CustomerProfile).where(CustomerProfile.user_id == user.id)
    )
    profile = result.first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return profile


async def place_orders_from_cart(
    session: AsyncSession, user: User, customer_address_id: int
) -> List[Order]:
    profile = await _customer_profile(session, user)
    assert profile.id is not None

    addr_result = await session.exec(
        select(CustomerAddress, Address)
        .join(Address, Address.id == CustomerAddress.address_id)  # type: ignore[arg-type]
        .where(CustomerAddress.id == customer_address_id)
    )
    addr_row = addr_result.first()
    if addr_row is None:
        raise HTTPException(status_code=404, detail="invalid_address")
    customer_address, address = addr_row
    if customer_address.customer_profile_id != profile.id:
        raise HTTPException(status_code=403, detail="invalid_address")
    address_snapshot = _format_address_snapshot(address)

    cart_result = await session.exec(select(Cart).where(Cart.customer_profile_id == profile.id))
    carts = list(cart_result.all())
    if not carts:
        raise HTTPException(status_code=400, detail="cart_empty")

    cart_ids = [c.id for c in carts if c.id is not None]
    items_result = await session.exec(
        select(CartItem).where(CartItem.cart_id.in_(cart_ids))  # type: ignore[attr-defined]
    )
    cart_items = list(items_result.all())
    if not cart_items:
        raise HTTPException(status_code=400, detail="cart_empty")

    inv_ids = [item.inventory_id for item in cart_items]
    locked_inv = await lock_inventory_rows(session, inv_ids)
    inv_by_id = {inv.id: inv for inv in locked_inv}

    # Validate availability before any writes.
    qty_by_inv: dict[int, int] = {}
    for item in cart_items:
        qty_by_inv[item.inventory_id] = qty_by_inv.get(item.inventory_id, 0) + item.quantity
    for inv_id, requested in qty_by_inv.items():
        inv = inv_by_id.get(inv_id)
        if inv is None or not inv.is_available:
            raise HTTPException(status_code=409, detail={"detail": "item_unavailable", "inventory_ids": [inv_id]})
        if inv.stock < requested:
            raise HTTPException(status_code=409, detail={
                "detail": "insufficient_stock",
                "item": {"inventory_id": inv_id, "available_stock": inv.stock, "requested": requested},
            })

    # Validate stores active.
    store_ids = [c.store_id for c in carts]
    stores_result = await session.exec(select(Store).where(Store.id.in_(store_ids)))  # type: ignore[attr-defined]
    stores_by_id = {s.id: s for s in stores_result.all()}
    for c in carts:
        store = stores_by_id.get(c.store_id)
        if store is None or not store.is_active:
            raise HTTPException(status_code=409, detail={"detail": "store_unavailable", "store_id": c.store_id})

    # Snapshot product names.
    products_result = await session.exec(
        select(MasterProduct, StoreInventory.id)
        .join(StoreInventory, StoreInventory.product_id == MasterProduct.id)  # type: ignore[arg-type]
        .where(StoreInventory.id.in_(inv_ids))  # type: ignore[attr-defined]
    )
    name_by_inv: dict[int, str] = {inv_id: product.name for product, inv_id in products_result.all()}

    items_by_cart: dict[int, list[CartItem]] = {}
    for item in cart_items:
        items_by_cart.setdefault(item.cart_id, []).append(item)

    created_orders: list[Order] = []
    for cart in carts:
        assert cart.id is not None
        items = items_by_cart.get(cart.id, [])
        if not items:
            continue
        subtotal = sum(inv_by_id[i.inventory_id].price * i.quantity for i in items)
        delivery_fee = 0.0
        tax = 0.0
        total = subtotal + delivery_fee + tax

        order = Order(
            customer_profile_id=profile.id,
            store_id=cart.store_id,
            delivery_address_id=address.id,
            delivery_address_snapshot=address_snapshot,
            status=OrderStatus.Pending,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            tax=tax,
            total=total,
        )
        session.add(order)
        await session.flush()
        assert order.id is not None

        for item in items:
            inv = inv_by_id[item.inventory_id]
            session.add(OrderItem(
                order_id=order.id,
                inventory_id=item.inventory_id,
                product_name_snapshot=name_by_inv.get(item.inventory_id, "Item"),
                unit_price_snapshot=inv.price,
                quantity=item.quantity,
                line_total=inv.price * item.quantity,
            ))
            await decrement_stock(session, item.inventory_id, item.quantity)

        session.add(Payment(
            order_id=order.id,
            amount=total,
            method=PaymentMethod.Cash,
            status=PaymentStatus.Pending,
        ))
        session.add(Delivery(order_id=order.id, status=DeliveryStatus.Pending))
        created_orders.append(order)

    # Clear cart.
    for item in cart_items:
        await session.delete(item)
    for cart in carts:
        await session.delete(cart)

    await session.commit()
    for order in created_orders:
        await session.refresh(order)
    return created_orders
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/src/app/services/checkout.py
git commit -m "feat(orders): add checkout service with row-locked stock validation"
```

---

## Task 11: Order serializer + GET endpoints + scoping helpers

**Files:**
- Create: `backend/app/src/app/api/orders.py`

- [ ] **Step 1: Create the file with helpers and read endpoints**

Create `backend/app/src/app/api/orders.py`:

```python
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import (
    get_current_admin,
    get_current_customer,
    get_current_seller,
    get_current_user,
)
from app.db.session import get_db_session
from app.models.base import User, UserRole
from app.models.commerce import (
    Delivery,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
)
from app.models.profile import CustomerProfile, SellerProfile
from app.models.store import Store
from app.schemas.orders import (
    DeliveryRead,
    OrderItemRead,
    OrderListResponse,
    OrderRead,
    PaymentRead,
)

router = APIRouter()

ACTIVE_STATUSES = (OrderStatus.Pending, OrderStatus.Packed, OrderStatus.Dispatched)
HISTORY_STATUSES = (OrderStatus.Delivered, OrderStatus.Cancelled)


async def _serialize_order(session: AsyncSession, order: Order, *, include_customer_name: bool) -> OrderRead:
    assert order.id is not None
    items_result = await session.exec(select(OrderItem).where(OrderItem.order_id == order.id))
    items = list(items_result.all())
    payment_result = await session.exec(select(Payment).where(Payment.order_id == order.id))
    payment = payment_result.first()
    delivery_result = await session.exec(select(Delivery).where(Delivery.order_id == order.id))
    delivery = delivery_result.first()
    store_result = await session.exec(select(Store).where(Store.id == order.store_id))
    store = store_result.first()
    customer_name: Optional[str] = None
    if include_customer_name:
        cust_result = await session.exec(
            select(CustomerProfile).where(CustomerProfile.id == order.customer_profile_id)
        )
        cust = cust_result.first()
        if cust is not None:
            customer_name = " ".join(p for p in (cust.first_name, cust.last_name) if p)
    return OrderRead(
        id=order.id,
        store_id=order.store_id,
        store_name=store.name if store else "",
        customer_name=customer_name,
        status=order.status,
        subtotal=order.subtotal,
        delivery_fee=order.delivery_fee,
        tax=order.tax,
        total=order.total,
        placed_at=order.placed_at,
        delivery_address_snapshot=order.delivery_address_snapshot,
        items=[OrderItemRead(
            id=i.id,  # type: ignore[arg-type]
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


def _status_filter_for(status_param: Optional[str]) -> Optional[tuple[OrderStatus, ...]]:
    if status_param is None:
        return None
    if status_param == "active":
        return ACTIVE_STATUSES
    if status_param == "history":
        return HISTORY_STATUSES
    raise HTTPException(status_code=400, detail="invalid_status_filter")


async def _seller_store_ids(session: AsyncSession, user: User) -> list[int]:
    profile_result = await session.exec(
        select(SellerProfile.id).where(SellerProfile.user_id == user.id)
    )
    profile_id = profile_result.first()
    if profile_id is None:
        return []
    store_result = await session.exec(
        select(Store.id).where(Store.seller_profile_id == profile_id)
    )
    return list(store_result.all())


async def _customer_profile_id(session: AsyncSession, user: User) -> int:
    result = await session.exec(
        select(CustomerProfile.id).where(CustomerProfile.user_id == user.id)
    )
    profile_id = result.first()
    if profile_id is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return profile_id


@router.get("", response_model=OrderListResponse)
@router.get("/", response_model=OrderListResponse, include_in_schema=False)
async def list_orders(
    status: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderListResponse:
    statuses = _status_filter_for(status)
    stmt = select(Order)
    include_customer = False

    if user.role == UserRole.Customer:
        profile_id = await _customer_profile_id(session, user)
        stmt = stmt.where(Order.customer_profile_id == profile_id)
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


async def _load_order_for_user(session: AsyncSession, order_id: int, user: User) -> tuple[Order, bool]:
    """Load an order, enforce role-based access, return (order, include_customer_name)."""
    result = await session.exec(select(Order).where(Order.id == order_id))
    order = result.first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if user.role == UserRole.Customer:
        profile_id = await _customer_profile_id(session, user)
        if order.customer_profile_id != profile_id:
            raise HTTPException(status_code=403, detail="forbidden")
        return order, False
    if user.role == UserRole.Seller:
        store_ids = await _seller_store_ids(session, user)
        if order.store_id not in store_ids:
            raise HTTPException(status_code=403, detail="forbidden")
        return order, True
    if user.role == UserRole.Admin:
        return order, True
    raise HTTPException(status_code=403, detail="forbidden")


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderRead:
    order, include_customer = await _load_order_for_user(session, order_id, user)
    return await _serialize_order(session, order, include_customer_name=include_customer)
```

- [ ] **Step 2: Mount the router**

Modify `backend/app/src/app/api/__init__.py` (alphabetical order):

```python
from app.api import auth, carts, catalog, customers, meta, orders, sellers, stores, tasks
```

```python
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
```

- [ ] **Step 3: Smoke check the import**

```bash
uv run python -c "from app import app; print('orders' in [r.tags[0] if r.tags else '' for r in app.routes if hasattr(r, 'tags') and r.tags])"
```

Expected: `True`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/api/orders.py backend/app/src/app/api/__init__.py
git commit -m "feat(orders): add GET /orders and GET /orders/{id}"
```

---

## Task 12: POST /orders endpoint + checkout tests

**Files:**
- Modify: `backend/app/src/app/api/orders.py`
- Create: `backend/app/tests/test_orders.py`

- [ ] **Step 1: Write failing tests**

Create `backend/app/tests/test_orders.py`:

```python
from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Category, MasterProduct
from app.models.commerce import (
    Cart,
    CartItem,
    Delivery,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
)
from app.models.profile import CustomerAddress, CustomerProfile, SellerProfile, VerificationStatus
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

mock_customer = User(id=301, email="ord-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_other_customer = User(id=302, email="ord-other@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=303, email="ord-seller@kb.com", role=UserRole.Seller, is_active=True)
mock_other_seller = User(id=304, email="ord-other-seller@kb.com", role=UserRole.Seller, is_active=True)
mock_admin = User(id=305, email="ord-admin@kb.com", role=UserRole.Admin, is_active=True)


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    """Seed two customers, two sellers each with a store, two inventory rows, addresses, plus a cart for the main customer."""
    for u in (mock_customer, mock_other_customer, mock_seller, mock_other_seller, mock_admin):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer_profile = CustomerProfile(user_id=mock_customer.id, first_name="Cust")
    other_customer_profile = CustomerProfile(user_id=mock_other_customer.id, first_name="Other")
    session.add_all([customer_profile, other_customer_profile])
    await session.flush()

    cust_addr = Address(**make_address(pincode="560050"))
    session.add(cust_addr)
    await session.flush()
    cust_address = CustomerAddress(
        customer_profile_id=customer_profile.id, address_id=cust_addr.id, is_default=True,
    )
    session.add(cust_address)

    seller_business_addr = Address(**make_address(pincode="560100"))
    session.add(seller_business_addr)
    await session.flush()
    seller_profile = SellerProfile(
        user_id=mock_seller.id, first_name="S1", phone="+919800000010",
        business_name="S1 Store", business_category="grocery",
        bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_business_addr.id,
    )
    session.add(seller_profile)

    other_seller_business_addr = Address(**make_address(pincode="560101"))
    session.add(other_seller_business_addr)
    await session.flush()
    other_seller_profile = SellerProfile(
        user_id=mock_other_seller.id, first_name="S2", phone="+919800000020",
        business_name="S2 Store", business_category="grocery",
        bank_account_number="2", bank_ifsc="HDFC0000002",
        verification_status=VerificationStatus.Approved,
        business_address_id=other_seller_business_addr.id,
    )
    session.add(other_seller_profile)
    await session.flush()

    store_addr = Address(**make_address(pincode="560110"))
    other_store_addr = Address(**make_address(pincode="560111"))
    session.add_all([store_addr, other_store_addr])
    await session.flush()

    store_a = Store(name="Store A", seller_profile_id=seller_profile.id, address_id=store_addr.id)
    store_b = Store(name="Store B", seller_profile_id=other_seller_profile.id, address_id=other_store_addr.id)
    session.add_all([store_a, store_b])
    await session.flush()

    category = Category(name="Food", slug="food")
    session.add(category)
    await session.flush()
    product = MasterProduct(name="Apple", slug="apple", category_id=category.id)
    product_b = MasterProduct(name="Bread", slug="bread", category_id=category.id)
    session.add_all([product, product_b])
    await session.flush()

    inv_a = StoreInventory(store_id=store_a.id, product_id=product.id, price=50.0, stock=10)
    inv_b = StoreInventory(store_id=store_b.id, product_id=product_b.id, price=30.0, stock=4)
    session.add_all([inv_a, inv_b])
    await session.flush()

    # Multi-store cart for main customer.
    cart_a = Cart(customer_profile_id=customer_profile.id, store_id=store_a.id)
    cart_b = Cart(customer_profile_id=customer_profile.id, store_id=store_b.id)
    session.add_all([cart_a, cart_b])
    await session.flush()
    session.add_all([
        CartItem(cart_id=cart_a.id, inventory_id=inv_a.id, quantity=2),
        CartItem(cart_id=cart_b.id, inventory_id=inv_b.id, quantity=1),
    ])
    await session.commit()

    yield {
        "customer_address_id": cust_address.id,
        "store_a": store_a.id,
        "store_b": store_b.id,
        "inv_a": inv_a.id,
        "inv_b": inv_b.id,
        "customer_profile": customer_profile.id,
        "seller_profile": seller_profile.id,
    }


def _override(user: User) -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def as_customer() -> Iterator[None]:
    yield from _override(mock_customer)


@pytest.fixture
def as_other_customer() -> Iterator[None]:
    yield from _override(mock_other_customer)


@pytest.fixture
def as_seller() -> Iterator[None]:
    yield from _override(mock_seller)


@pytest.fixture
def as_other_seller() -> Iterator[None]:
    yield from _override(mock_other_seller)


@pytest.fixture
def as_admin() -> Iterator[None]:
    yield from _override(mock_admin)


async def test_place_orders_fans_out_per_store(as_customer: Any, seed: dict[str, int], session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/orders", json={"customer_address_id": seed["customer_address_id"]})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["orders"]) == 2
    totals = sorted(o["total"] for o in body["orders"])
    assert totals == [30.0, 100.0]

    orders = (await session.exec(select(Order))).all()
    assert len(orders) == 2
    payments = (await session.exec(select(Payment))).all()
    assert len(payments) == 2
    assert all(p.status == PaymentStatus.Pending for p in payments)
    deliveries = (await session.exec(select(Delivery))).all()
    assert len(deliveries) == 2
    items = (await session.exec(select(OrderItem))).all()
    assert {i.product_name_snapshot for i in items} == {"Apple", "Bread"}

    inv_a = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_a"]))).first()
    inv_b = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_b"]))).first()
    assert inv_a.stock == 8
    assert inv_b.stock == 3

    remaining_carts = (await session.exec(select(Cart))).all()
    assert remaining_carts == []


async def test_place_orders_empty_cart(as_other_customer: Any, seed: dict[str, int]) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/orders", json={"customer_address_id": seed["customer_address_id"]})
    assert resp.status_code in (400, 403)


async def test_place_orders_invalid_address(as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/orders", json={"customer_address_id": 9999})
    assert resp.status_code == 404


async def test_place_orders_insufficient_stock(as_customer: Any, seed: dict[str, int], session: AsyncSession) -> None:
    inv = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_a"]))).first()
    inv.stock = 1   # cart wants 2
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/orders", json={"customer_address_id": seed["customer_address_id"]})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["detail"] == "insufficient_stock"
    # Both stocks unchanged on rollback.
    inv = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_a"]))).first()
    inv_b = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_b"]))).first()
    assert inv.stock == 1 and inv_b.stock == 4
    assert (await session.exec(select(Order))).all() == []
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_orders.py -v -k "place_orders"
```

Expected: 4 failures (route missing).

- [ ] **Step 3: Add the endpoint**

Append to `backend/app/src/app/api/orders.py`:

```python
from app.schemas.orders import PlaceOrderRequest, PlaceOrderResponse
from app.services.checkout import place_orders_from_cart
from fastapi import status

@router.post("", response_model=PlaceOrderResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=PlaceOrderResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def place_order(
    payload: PlaceOrderRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> PlaceOrderResponse:
    orders = await place_orders_from_cart(session, user, payload.customer_address_id)
    return PlaceOrderResponse(
        orders=[await _serialize_order(session, o, include_customer_name=False) for o in orders]
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_orders.py -v -k "place_orders"
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/orders.py backend/app/tests/test_orders.py
git commit -m "feat(orders): add POST /orders checkout endpoint"
```

---

## Task 13: GET /orders + GET /orders/{id} tests

**Files:**
- Modify: `backend/app/tests/test_orders.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/app/tests/test_orders.py`:

```python
async def _place_orders(seed: dict[str, int]) -> list[int]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/orders", json={"customer_address_id": seed["customer_address_id"]})
    assert resp.status_code == 201, resp.text
    return [o["id"] for o in resp.json()["orders"]]


async def test_customer_lists_only_their_orders(as_customer: Any, seed: dict[str, int]) -> None:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    order_ids = await _place_orders(seed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/orders")
    assert resp.status_code == 200
    assert sorted(o["id"] for o in resp.json()["orders"]) == sorted(order_ids)


async def test_seller_lists_only_their_store_orders(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/orders")
    assert resp.status_code == 200
    orders = resp.json()["orders"]
    assert len(orders) == 1   # only Store A is theirs
    assert orders[0]["store_id"] == seed["store_a"]
    assert orders[0]["customer_name"] == "Cust"


async def test_admin_lists_all_orders(as_customer: Any, seed: dict[str, int]) -> None:
    await _place_orders(seed)
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/orders")
    assert resp.status_code == 200
    assert len(resp.json()["orders"]) == 2


async def test_active_filter(as_customer: Any, seed: dict[str, int]) -> None:
    await _place_orders(seed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/orders?status=active")
    assert resp.status_code == 200
    assert len(resp.json()["orders"]) == 2


async def test_get_order_detail(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/orders/{order_ids[0]}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["payment"]["status"] == "pending"
    assert body["delivery"]["status"] == "pending"
    assert len(body["items"]) == 1


async def test_other_seller_cannot_see_order(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    # store_a is owned by mock_seller; mock_other_seller should be 403
    app.dependency_overrides[get_current_user] = lambda: mock_other_seller
    target_id = order_ids[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/orders/{target_id}")
    assert resp.status_code in (200, 403)
    # If the first id happens to be store_b's order, swap to the other.
    if resp.status_code == 200:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/orders/{order_ids[1]}")
        assert resp.status_code == 403
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_orders.py -v
```

Expected: all passing.

- [ ] **Step 3: Commit**

```bash
git add backend/app/tests/test_orders.py
git commit -m "test(orders): cover list and detail role scoping"
```

---

## Task 14: Order state machine service

**Files:**
- Create: `backend/app/src/app/services/orders.py`

- [ ] **Step 1: Create the service**

Create `backend/app/src/app/services/orders.py`:

```python
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User, UserRole
from app.models.commerce import (
    Delivery,
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
)
from app.models.profile import CustomerProfile, SellerProfile
from app.models.store import Store
from app.services.inventory import restock

LEGAL_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.Pending: {OrderStatus.Packed, OrderStatus.Cancelled},
    OrderStatus.Packed: {OrderStatus.Dispatched, OrderStatus.Cancelled},
    OrderStatus.Dispatched: {OrderStatus.Delivered, OrderStatus.Cancelled},
    OrderStatus.Delivered: set(),
    OrderStatus.Cancelled: set(),
}

TARGET_BY_STR: dict[str, OrderStatus] = {
    "packed": OrderStatus.Packed,
    "dispatched": OrderStatus.Dispatched,
    "delivered": OrderStatus.Delivered,
}


async def _seller_owns_store(session: AsyncSession, user: User, store_id: int) -> bool:
    profile_result = await session.exec(
        select(SellerProfile.id).where(SellerProfile.user_id == user.id)
    )
    profile_id = profile_result.first()
    if profile_id is None:
        return False
    store_result = await session.exec(
        select(Store.id).where(Store.id == store_id, Store.seller_profile_id == profile_id)
    )
    return store_result.first() is not None


async def transition_order_status(
    session: AsyncSession, order: Order, target_str: Literal["packed", "dispatched", "delivered"], actor: User,
) -> Order:
    target = TARGET_BY_STR[target_str]
    if target not in LEGAL_TRANSITIONS.get(order.status, set()):
        raise HTTPException(status_code=409, detail={
            "detail": "illegal_transition", "from": order.status.value, "to": target.value,
        })

    # Authorization: seller owns store or admin.
    if actor.role == UserRole.Seller:
        if not await _seller_owns_store(session, actor, order.store_id):
            raise HTTPException(status_code=403, detail="forbidden")
    elif actor.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="forbidden")

    delivery_result = await session.exec(select(Delivery).where(Delivery.order_id == order.id))
    delivery = delivery_result.first()
    if delivery is None:
        raise HTTPException(status_code=500, detail="delivery_missing")

    now = datetime.now(timezone.utc)
    order.status = target
    if target == OrderStatus.Packed:
        delivery.status = DeliveryStatus.Packed
        delivery.packed_at = now
    elif target == OrderStatus.Dispatched:
        delivery.status = DeliveryStatus.Dispatched
        delivery.dispatched_at = now
    elif target == OrderStatus.Delivered:
        delivery.status = DeliveryStatus.Delivered
        delivery.delivered_at = now
        payment_result = await session.exec(select(Payment).where(Payment.order_id == order.id))
        payment = payment_result.first()
        if payment is not None:
            payment.status = PaymentStatus.Paid
            payment.paid_at = now

    await session.commit()
    await session.refresh(order)
    return order


async def cancel_order(session: AsyncSession, order: Order, actor: User) -> Order:
    if order.status in (OrderStatus.Delivered, OrderStatus.Cancelled):
        raise HTTPException(status_code=409, detail="terminal_status")

    if actor.role == UserRole.Customer:
        if order.status != OrderStatus.Pending:
            raise HTTPException(status_code=403, detail="cancel_not_allowed")
        cust_result = await session.exec(
            select(CustomerProfile.id).where(CustomerProfile.user_id == actor.id)
        )
        if cust_result.first() != order.customer_profile_id:
            raise HTTPException(status_code=403, detail="forbidden")
    elif actor.role == UserRole.Seller:
        if not await _seller_owns_store(session, actor, order.store_id):
            raise HTTPException(status_code=403, detail="forbidden")
    elif actor.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="forbidden")

    delivery_result = await session.exec(select(Delivery).where(Delivery.order_id == order.id))
    delivery = delivery_result.first()
    payment_result = await session.exec(select(Payment).where(Payment.order_id == order.id))
    payment = payment_result.first()

    order.status = OrderStatus.Cancelled
    if delivery is not None:
        delivery.status = DeliveryStatus.Cancelled
    if payment is not None and payment.status == PaymentStatus.Paid:
        payment.status = PaymentStatus.Refunded

    items_result = await session.exec(select(OrderItem).where(OrderItem.order_id == order.id))
    for item in items_result.all():
        if item.inventory_id is not None:
            await restock(session, item.inventory_id, item.quantity)

    await session.commit()
    await session.refresh(order)
    return order
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/src/app/services/orders.py
git commit -m "feat(orders): add transition + cancel state machine"
```

---

## Task 15: POST /orders/{id}/transition + tests

**Files:**
- Modify: `backend/app/src/app/api/orders.py`
- Modify: `backend/app/tests/test_orders.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/app/tests/test_orders.py`:

```python
async def test_seller_marks_packed(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    target = order_ids[0] if (await __get_order_store(order_ids[0])) == seed["store_a"] else order_ids[1]

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "packed"
    assert resp.json()["delivery"]["status"] == "packed"


async def test_illegal_transition(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    target = order_ids[0] if (await __get_order_store(order_ids[0])) == seed["store_a"] else order_ids[1]

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "delivered"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["detail"] == "illegal_transition"


async def test_other_seller_cannot_transition(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    target = order_ids[0] if (await __get_order_store(order_ids[0])) == seed["store_a"] else order_ids[1]

    app.dependency_overrides[get_current_user] = lambda: mock_other_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
    assert resp.status_code == 403


async def test_delivered_marks_payment_paid(as_customer: Any, seed: dict[str, int], session: AsyncSession) -> None:
    order_ids = await _place_orders(seed)
    target = order_ids[0] if (await __get_order_store(order_ids[0])) == seed["store_a"] else order_ids[1]

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "dispatched"})
        resp = await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "delivered"})
    assert resp.status_code == 200
    assert resp.json()["payment"]["status"] == "paid"
    assert resp.json()["payment"]["paid_at"] is not None


async def __get_order_store(order_id: int) -> int:
    """Helper: peek an order's store_id from the DB."""
    from app.db.session import engine
    from sqlmodel.ext.asyncio.session import AsyncSession as S
    async with S(engine) as s:
        return (await s.exec(select(Order.store_id).where(Order.id == order_id))).first()
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_orders.py -v -k "marks_packed or illegal_transition or other_seller_cannot_transition or delivered_marks_payment"
```

Expected: 4 failures.

- [ ] **Step 3: Implement the endpoint**

Append to `backend/app/src/app/api/orders.py`:

```python
from app.schemas.orders import TransitionRequest
from app.services.orders import transition_order_status, cancel_order


@router.post("/{order_id}/transition", response_model=OrderRead)
async def transition_order(
    order_id: int,
    payload: TransitionRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderRead:
    if user.role not in (UserRole.Seller, UserRole.Admin):
        raise HTTPException(status_code=403, detail="forbidden")
    order, include_customer = await _load_order_for_user(session, order_id, user)
    order = await transition_order_status(session, order, payload.to, user)
    return await _serialize_order(session, order, include_customer_name=include_customer)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_orders.py -v
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/orders.py backend/app/tests/test_orders.py
git commit -m "feat(orders): add POST /orders/{id}/transition"
```

---

## Task 16: POST /orders/{id}/cancel + tests

**Files:**
- Modify: `backend/app/src/app/api/orders.py`
- Modify: `backend/app/tests/test_orders.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/app/tests/test_orders.py`:

```python
async def test_customer_cancels_pending(as_customer: Any, seed: dict[str, int], session: AsyncSession) -> None:
    order_ids = await _place_orders(seed)
    target = order_ids[0]
    pre_stock = (await session.exec(select(StoreInventory.stock).where(StoreInventory.id == seed["inv_a"]))).first()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    target_store = (await session.exec(select(Order.store_id).where(Order.id == target))).first()
    if target_store == seed["store_a"]:
        post_stock = (await session.exec(select(StoreInventory.stock).where(StoreInventory.id == seed["inv_a"]))).first()
        assert post_stock == pre_stock + 2


async def test_customer_cannot_cancel_after_pack(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Pack store_a's order
        for oid in order_ids:
            store = await __get_order_store(oid)
            if store == seed["store_a"]:
                await ac.post(f"/api/v1/orders/{oid}/transition", json={"to": "packed"})
                target = oid
                break

    app.dependency_overrides[get_current_user] = lambda: mock_customer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/cancel")
    assert resp.status_code == 403


async def test_seller_cancels_packed_order(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    target = next(oid for oid in order_ids if (await __get_order_store(oid)) == seed["store_a"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
        resp = await ac.post(f"/api/v1/orders/{target}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_admin_cancels_dispatched_order(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    target = next(oid for oid in order_ids if (await __get_order_store(oid)) == seed["store_a"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "dispatched"})

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/cancel")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_orders.py -v -k "cancel"
```

Expected: 4 failures.

- [ ] **Step 3: Implement endpoint**

Append to `backend/app/src/app/api/orders.py`:

```python
@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel(
    order_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderRead:
    order, include_customer = await _load_order_for_user(session, order_id, user)
    order = await cancel_order(session, order, user)
    return await _serialize_order(session, order, include_customer_name=include_customer)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_orders.py -v
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/orders.py backend/app/tests/test_orders.py
git commit -m "feat(orders): add POST /orders/{id}/cancel"
```

---

## Task 17: Celery email tasks + tests

**Files:**
- Modify: `backend/app/src/app/worker.py`
- Create: `backend/app/src/app/services/order_emails.py`
- Create: `backend/app/tests/test_order_emails.py`

- [ ] **Step 1: Write failing test**

Create `backend/app/tests/test_order_emails.py`:

```python
from typing import Any
from unittest.mock import patch

import pytest


@pytest.mark.parametrize("task_name,args", [
    ("send_order_placed_seller_async", (1,)),
    ("send_order_confirmed_customer_async", ([1, 2],)),
    ("send_order_status_changed_async", (1, "packed")),
])
def test_email_tasks_callable_in_console_mode(task_name: str, args: tuple[Any, ...]) -> None:
    from app import worker
    with patch("app.core.config.settings.EMAIL_PROVIDER", "console"):
        fn = getattr(worker, task_name)
        result = fn(*args)
    assert result is None
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_order_emails.py -v
```

Expected: AttributeError or ImportError.

- [ ] **Step 3: Add tasks**

Append to `backend/app/src/app/worker.py`:

```python
def _resolve_email(to: str, subject: str, body: str) -> None:
    from app.core.config import settings
    if settings.EMAIL_PROVIDER == "resend":
        import httpx
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.RESEND_FROM_EMAIL,
                "to": [to],
                "subject": subject,
                "text": body,
            },
            timeout=10,
        )
        resp.raise_for_status()
    else:
        logging.getLogger(__name__).info("EMAIL to=%s subject=%s", to, subject)


def _load_order_email_context(order_id: int) -> dict[str, Any]:
    """Load order, store, customer email synchronously for Celery."""
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession
    from app.core.config import settings
    from app.models.base import User
    from app.models.commerce import Order
    from app.models.profile import CustomerProfile, SellerProfile
    from app.models.store import Store

    async def _load() -> dict[str, Any]:
        engine = create_async_engine(settings.DATABASE_URL)
        async with AsyncSession(engine) as s:
            order = (await s.exec(select(Order).where(Order.id == order_id))).first()
            if order is None:
                return {}
            store = (await s.exec(select(Store).where(Store.id == order.store_id))).first()
            seller_profile = None
            if store is not None:
                seller_profile = (await s.exec(
                    select(SellerProfile).where(SellerProfile.id == store.seller_profile_id)
                )).first()
            seller_user = None
            if seller_profile is not None:
                seller_user = (await s.exec(
                    select(User).where(User.id == seller_profile.user_id)
                )).first()
            customer_profile = (await s.exec(
                select(CustomerProfile).where(CustomerProfile.id == order.customer_profile_id)
            )).first()
            customer_user = None
            if customer_profile is not None:
                customer_user = (await s.exec(
                    select(User).where(User.id == customer_profile.user_id)
                )).first()
            return {
                "order_id": order.id,
                "store_name": store.name if store else "",
                "total": order.total,
                "status": order.status.value,
                "customer_email": customer_user.email if customer_user else None,
                "seller_email": seller_user.email if seller_user else None,
            }

    return asyncio.run(_load())


@celery_app.task(name="send_order_placed_seller_async", autoretry_for=(Exception,), max_retries=3, retry_backoff=True)  # type: ignore[untyped-decorator]
def send_order_placed_seller_async(order_id: int) -> None:
    ctx = _load_order_email_context(order_id)
    if not ctx or not ctx.get("seller_email"):
        return
    _resolve_email(
        ctx["seller_email"],
        f"New order #{ctx['order_id']} on {ctx['store_name']}",
        f"You have a new order. Total ₹{ctx['total']:.2f}. Open the dashboard to pack it.",
    )


@celery_app.task(name="send_order_confirmed_customer_async", autoretry_for=(Exception,), max_retries=3, retry_backoff=True)  # type: ignore[untyped-decorator]
def send_order_confirmed_customer_async(order_ids: list[int]) -> None:
    if not order_ids:
        return
    contexts = [_load_order_email_context(oid) for oid in order_ids]
    contexts = [c for c in contexts if c]
    if not contexts:
        return
    customer_email = contexts[0].get("customer_email")
    if not customer_email:
        return
    lines = [f"#{c['order_id']} from {c['store_name']} — ₹{c['total']:.2f}" for c in contexts]
    _resolve_email(
        customer_email,
        f"Order confirmation ({len(contexts)} order{'s' if len(contexts) > 1 else ''})",
        "Thank you for your order:\n\n" + "\n".join(lines),
    )


@celery_app.task(name="send_order_status_changed_async", autoretry_for=(Exception,), max_retries=3, retry_backoff=True)  # type: ignore[untyped-decorator]
def send_order_status_changed_async(order_id: int, new_status: str) -> None:
    ctx = _load_order_email_context(order_id)
    if not ctx or not ctx.get("customer_email"):
        return
    _resolve_email(
        ctx["customer_email"],
        f"Order #{ctx['order_id']} update: {new_status}",
        f"Your order from {ctx['store_name']} is now {new_status}.",
    )
```

- [ ] **Step 4: Add a thin dispatcher service**

Create `backend/app/src/app/services/order_emails.py`:

```python
"""Tiny wrappers so business code calls plain functions, not Celery API."""
from app.worker import (
    send_order_confirmed_customer_async,
    send_order_placed_seller_async,
    send_order_status_changed_async,
)


def dispatch_order_placed(order_ids: list[int], customer_order_ids: list[int]) -> None:
    for oid in order_ids:
        send_order_placed_seller_async.delay(oid)
    if customer_order_ids:
        send_order_confirmed_customer_async.delay(customer_order_ids)


def dispatch_order_status_changed(order_id: int, new_status: str) -> None:
    send_order_status_changed_async.delay(order_id, new_status)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_order_emails.py -v
```

Expected: 3 passed (console mode short-circuits the HTTP call).

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/worker.py backend/app/src/app/services/order_emails.py backend/app/tests/test_order_emails.py
git commit -m "feat(orders): add celery email tasks and dispatcher"
```

---

## Task 18: Wire email dispatch into checkout, transitions, cancel

**Files:**
- Modify: `backend/app/src/app/api/orders.py`

- [ ] **Step 1: Inject dispatch on checkout**

Modify the `place_order` handler in `backend/app/src/app/api/orders.py` to dispatch emails after the service returns:

```python
from app.services.order_emails import dispatch_order_placed, dispatch_order_status_changed


@router.post("", response_model=PlaceOrderResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=PlaceOrderResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def place_order(
    payload: PlaceOrderRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> PlaceOrderResponse:
    orders = await place_orders_from_cart(session, user, payload.customer_address_id)
    order_ids = [o.id for o in orders if o.id is not None]
    dispatch_order_placed(order_ids, order_ids)
    return PlaceOrderResponse(
        orders=[await _serialize_order(session, o, include_customer_name=False) for o in orders]
    )
```

- [ ] **Step 2: Inject dispatch on transitions**

Modify `transition_order` to dispatch after the service call:

```python
@router.post("/{order_id}/transition", response_model=OrderRead)
async def transition_order(
    order_id: int,
    payload: TransitionRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderRead:
    if user.role not in (UserRole.Seller, UserRole.Admin):
        raise HTTPException(status_code=403, detail="forbidden")
    order, include_customer = await _load_order_for_user(session, order_id, user)
    order = await transition_order_status(session, order, payload.to, user)
    if order.id is not None:
        dispatch_order_status_changed(order.id, order.status.value)
    return await _serialize_order(session, order, include_customer_name=include_customer)
```

- [ ] **Step 3: Inject dispatch on cancel**

Modify `cancel`:

```python
@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel(
    order_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderRead:
    order, include_customer = await _load_order_for_user(session, order_id, user)
    order = await cancel_order(session, order, user)
    if order.id is not None:
        dispatch_order_status_changed(order.id, "cancelled")
    return await _serialize_order(session, order, include_customer_name=include_customer)
```

- [ ] **Step 4: Verify tests still pass**

`.delay()` works in eager mode if Celery is configured; if not, dispatches happen against the broker. Either way, in-process tests should not crash because we use `.delay()` (which queues). Verify:

```bash
uv run pytest tests/test_orders.py tests/test_carts.py tests/test_order_emails.py -v
```

If `.delay()` blows up because Redis is not reachable in CI, set `CELERY_TASK_ALWAYS_EAGER=true` in test environment, or wrap the dispatchers in `try/except` that logs and continues.

- [ ] **Step 5: Add safety wrap if needed**

If Step 4 fails on broker connection, modify `services/order_emails.py` to swallow the dispatch error:

```python
import logging

_logger = logging.getLogger(__name__)


def _safe_delay(task: Any, *args: Any, **kwargs: Any) -> None:
    try:
        task.delay(*args, **kwargs)
    except Exception:
        _logger.exception("Celery dispatch failed; continuing")


def dispatch_order_placed(order_ids: list[int], customer_order_ids: list[int]) -> None:
    for oid in order_ids:
        _safe_delay(send_order_placed_seller_async, oid)
    if customer_order_ids:
        _safe_delay(send_order_confirmed_customer_async, customer_order_ids)


def dispatch_order_status_changed(order_id: int, new_status: str) -> None:
    _safe_delay(send_order_status_changed_async, order_id, new_status)
```

Re-run tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/api/orders.py backend/app/src/app/services/order_emails.py
git commit -m "feat(orders): dispatch email tasks on place/transition/cancel"
```

---

## Task 19: Final integration sanity + documentation

**Files:**
- (No code changes; verification only)

- [ ] **Step 1: Run the entire test suite**

```bash
uv run pytest -v
```

Expected: full green.

- [ ] **Step 2: Lint and type-check**

```bash
uv run ruff check .
uv run mypy .
```

Expected: clean.

- [ ] **Step 3: Manual smoke against running server**

In one terminal:

```bash
uv run uvicorn app.main:app --reload
```

In another, hit Swagger at `http://localhost:8000/docs` and verify the new sections appear: `carts`, `orders`. Open each endpoint and confirm the schemas render.

- [ ] **Step 4: Push branch and open PR**

(Wait for explicit user approval before this step.)

```bash
git push -u origin <branch>
gh pr create --title "feat(orders): backend cart persistence + checkout + state machine" --body "$(cat <<'EOF'
## Summary
- DB-backed customer cart with per-customer scoping and a sync endpoint for localStorage→DB merge on login.
- Single-button multi-store checkout that fans into one Order per store atomically with row-locked stock validation, snapshotted prices/names, and a cleared cart on success.
- Seller-driven status lifecycle (Pending → Packed → Dispatched → Delivered) with COD payment auto-flipping to Paid on Delivered. Cancellation by customer (Pending only), seller (pre-Delivered), or admin (any non-terminal), with stock restock.
- Three Celery tasks send order placed (seller), confirmation (customer), and status-changed (customer) emails via the existing Resend pattern.
- Single Alembic migration: composite indexes on (store_id, status) and (customer_profile_id, status), `delivery_address_snapshot` column, `orderitem.inventory_id ON DELETE SET NULL`.

## Test plan
- [ ] `uv run pytest -v` passes.
- [ ] `uv run ruff check .` and `uv run mypy .` clean.
- [ ] Swagger lists carts and orders sections under `/api/v1`.
- [ ] Manual: place an order via Swagger, confirm Order + OrderItem + Payment + Delivery rows in DB and stock decremented.
- [ ] Manual: transition Pending → Packed → Dispatched → Delivered; confirm Payment flipped to Paid.
- [ ] Manual: cancel a Pending order as customer; confirm stock restored.

## Migration / env-var notes
- Run `uv run alembic upgrade head`.
- No new env vars.
EOF
)"
```

---

## Self-Review Checklist (run after writing all tasks above)

- [ ] Every task in the spec is covered: cart CRUD ✓, sync ✓, checkout fan-out ✓, state machine ✓, role scoping ✓, cancel + restock ✓, COD flip on Delivered ✓, snapshotted address + product names ✓, indexes ✓, Celery emails ✓.
- [ ] No "TBD", "TODO", or "implement later" placeholders.
- [ ] Type/method names consistent: `place_orders_from_cart`, `transition_order_status`, `cancel_order`, `dispatch_order_placed`, `dispatch_order_status_changed`, `LEGAL_TRANSITIONS`, `TARGET_BY_STR`, `_serialize_order`, `_load_order_for_user`, `_customer_profile_id`.
- [ ] All imports referenced in test files exist in the codebase or are added in earlier tasks.
- [ ] Migration column nullability + FK matches the SQLModel field changes in Task 1, Step 3.
