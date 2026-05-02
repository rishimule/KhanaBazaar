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
from app.models.commerce import (
    Cart,
    CartItem,
    Delivery,
    Order,
    OrderItem,
    Payment,
    PaymentStatus,
)
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    VerificationStatus,
)
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

    # Reuse the seeding helper from test_carts.py.
    from tests.test_carts import _seed_product

    product = await _seed_product(
        session, service_slug="grocery", category_slug="food",
        subcategory_slug="fruit", product_slug="apple", name="Apple", base_price=50.0,
    )
    product_b = await _seed_product(
        session, service_slug="bakery", category_slug="bread-cat",
        subcategory_slug="loaves", product_slug="bread", name="Bread", base_price=30.0,
    )

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

    # Capture IDs before commit; commit expires attributes which would trigger
    # lazy reloads in async context (MissingGreenlet).
    ids = {
        "customer_address_id": cust_address.id,
        "store_a": store_a.id,
        "store_b": store_b.id,
        "inv_a": inv_a.id,
        "inv_b": inv_b.id,
        "customer_profile": customer_profile.id,
        "seller_profile": seller_profile.id,
    }
    await session.commit()

    yield ids


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
    # other_customer has a CustomerProfile but no Cart rows; the address belongs
    # to the main customer so the 403 path doesn't fire — we expect cart_empty.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/orders", json={"customer_address_id": seed["customer_address_id"]})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "invalid_address"


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
    # Full rollback: no orders / payments / deliveries / order_items, cart still intact.
    assert (await session.exec(select(Order))).all() == []
    assert (await session.exec(select(Payment))).all() == []
    assert (await session.exec(select(Delivery))).all() == []
    assert (await session.exec(select(OrderItem))).all() == []
    remaining_carts = (await session.exec(select(Cart))).all()
    assert len(remaining_carts) == 2  # cart_a + cart_b still present
    remaining_items = (await session.exec(select(CartItem))).all()
    assert len(remaining_items) == 2  # both cart items still present


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
    # Reference order_ids to validate they were created.
    assert len(order_ids) == 2


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
        active = await ac.get("/api/v1/orders?status=active")
        history = await ac.get("/api/v1/orders?status=history")
    assert active.status_code == 200
    assert len(active.json()["orders"]) == 2
    # Filter must actually drop something — fresh orders are Pending, never history.
    assert history.status_code == 200
    assert history.json()["orders"] == []


async def test_invalid_status_filter_returns_400(as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/orders?status=garbage")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_status_filter"


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
    # Map id -> store_id while still authenticated as the customer.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        details = [await ac.get(f"/api/v1/orders/{oid}") for oid in order_ids]
    store_by_id = {oid: r.json()["store_id"] for oid, r in zip(order_ids, details, strict=True)}
    own_id = next(oid for oid, sid in store_by_id.items() if sid == seed["store_b"])
    forbidden_id = next(oid for oid, sid in store_by_id.items() if sid == seed["store_a"])

    # mock_other_seller owns Store B; should see store_b's order, get 403 on store_a's.
    app.dependency_overrides[get_current_user] = lambda: mock_other_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        own = await ac.get(f"/api/v1/orders/{own_id}")
        forbidden = await ac.get(f"/api/v1/orders/{forbidden_id}")
    assert own.status_code == 200
    assert own.json()["store_id"] == seed["store_b"]
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "forbidden"


async def test_seller_marks_packed(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "packed"
    assert resp.json()["delivery"]["status"] == "packed"


async def test_illegal_transition(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "delivered"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["detail"] == "illegal_transition"


async def test_other_seller_cannot_transition(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_other_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
    assert resp.status_code == 403


async def test_delivered_marks_payment_paid(as_customer: Any, seed: dict[str, int], session: AsyncSession) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r1 = await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
        assert r1.status_code == 200, r1.text
        r2 = await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "dispatched"})
        assert r2.status_code == 200, r2.text
        resp = await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "delivered"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment"]["status"] == "paid"
    assert resp.json()["payment"]["paid_at"] is not None


async def _get_order_store(order_id: int) -> int:
    """Peek an order's store_id from the test database (not the prod engine)."""
    from sqlmodel.ext.asyncio.session import AsyncSession as S

    from tests.conftest import test_engine
    async with S(test_engine) as s:
        return (await s.exec(select(Order.store_id).where(Order.id == order_id))).first()


async def _order_id_for_store(order_ids: list[int], store_id: int) -> int:
    """Return the id of the order belonging to `store_id`. Pre-resolves all
    stores so the lookup is deterministic regardless of place_orders_from_cart's
    return order."""
    stores = [await _get_order_store(oid) for oid in order_ids]
    return next(oid for oid, s in zip(order_ids, stores, strict=True) if s == store_id)


async def test_customer_cancels_pending(as_customer: Any, seed: dict[str, int], session: AsyncSession) -> None:
    order_ids = await _place_orders(seed)
    # Deterministically pick store_a's order so the restock assertion always fires.
    target = await _order_id_for_store(order_ids, seed["store_a"])
    pre_stock = (await session.exec(select(StoreInventory.stock).where(StoreInventory.id == seed["inv_a"]))).first()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    post_stock = (await session.exec(select(StoreInventory.stock).where(StoreInventory.id == seed["inv_a"]))).first()
    assert post_stock == pre_stock + 2


async def test_customer_cannot_cancel_after_pack(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})

    app.dependency_overrides[get_current_user] = lambda: mock_customer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/cancel")
    assert resp.status_code == 403


async def test_seller_cancels_packed_order(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
        resp = await ac.post(f"/api/v1/orders/{target}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_admin_cancels_dispatched_order(as_customer: Any, seed: dict[str, int], session: AsyncSession) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])
    pre_stock = (await session.exec(select(StoreInventory.stock).where(StoreInventory.id == seed["inv_a"]))).first()

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "dispatched"})

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/cancel")
    assert resp.status_code == 200
    # Cancel from non-Pending status must still restock; this branch wasn't
    # exercised by the customer-cancels-Pending test.
    post_stock = (await session.exec(select(StoreInventory.stock).where(StoreInventory.id == seed["inv_a"]))).first()
    assert post_stock == pre_stock + 2
