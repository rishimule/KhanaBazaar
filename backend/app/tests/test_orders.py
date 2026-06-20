# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator, Iterator
from datetime import date, datetime, timedelta, timezone
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
    SellerProfileService,
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
        business_name="S1 Store",
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
        business_name="S2 Store",
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

    product, grocery_service_id = await _seed_product(
        session, service_slug="grocery", category_slug="food",
        subcategory_slug="fruit", product_slug="apple", name="Apple", base_price=50.0,
    )
    product_b, bakery_service_id = await _seed_product(
        session, service_slug="bakery", category_slug="bread-cat",
        subcategory_slug="loaves", product_slug="bread", name="Bread", base_price=30.0,
    )

    # Bind each seller to the service its store sells. Task 12 will add
    # _validate_service_active_for_store to the checkout path; this row keeps
    # every place-order call in this file valid once that lands.
    session.add(SellerProfileService(seller_profile_id=seller_profile.id, service_id=grocery_service_id))
    session.add(SellerProfileService(seller_profile_id=other_seller_profile.id, service_id=bakery_service_id))
    await session.flush()

    inv_a = StoreInventory(store_id=store_a.id, product_id=product.id, price=50.0, stock=10)
    inv_b = StoreInventory(store_id=store_b.id, product_id=product_b.id, price=30.0, stock=4)
    session.add_all([inv_a, inv_b])
    await session.flush()

    # Multi-store cart for main customer.
    cart_a = Cart(customer_profile_id=customer_profile.id, store_id=store_a.id, service_id=grocery_service_id)
    cart_b = Cart(customer_profile_id=customer_profile.id, store_id=store_b.id, service_id=bakery_service_id)
    session.add_all([cart_a, cart_b])
    await session.flush()
    session.add_all([
        CartItem(cart_id=cart_a.id, inventory_id=inv_a.id, quantity=2),
        CartItem(cart_id=cart_b.id, inventory_id=inv_b.id, quantity=1),
    ])

    # Capture IDs before commit; commit expires attributes which would trigger
    # lazy reloads in async context (MissingGreenlet).
    assert cust_address.id is not None
    assert store_a.id is not None
    assert store_b.id is not None
    assert inv_a.id is not None
    assert inv_b.id is not None
    assert customer_profile.id is not None
    assert seller_profile.id is not None
    ids: dict[str, int] = {
        "customer_address_id": cust_address.id,
        "store_a": store_a.id,
        "store_b": store_b.id,
        "inv_a": inv_a.id,
        "inv_b": inv_b.id,
        "customer_profile": customer_profile.id,
        "seller_profile": seller_profile.id,
        "grocery_service_id": grocery_service_id,
        "bakery_service_id": bakery_service_id,
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


async def test_place_order_for_store_creates_single_order_upi(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_a"],
                "service_id": seed["grocery_service_id"],
                "payment_method": "upi",
            },
        )
    assert resp.status_code == 201, resp.text
    # The order is placed in a separate request session. This test's session has
    # `expire_on_commit=False`, so seeded rows it already loaded (e.g. inv_a) stay
    # cached at their pre-request values and a plain SELECT returns the stale
    # identity-mapped instance. Expire so the DB-state assertions below re-read
    # the request session's committed changes (the inventory decrement).
    session.expire_all()
    body = resp.json()
    assert body["store_id"] == seed["store_a"]
    assert body["service_id"] == seed["grocery_service_id"]
    assert body["service_name"] == "Apple"
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


async def test_place_order_cart_not_found_for_store(
    as_other_customer: Any, seed: dict[str, int]
) -> None:
    # other_customer has a CustomerProfile but no cart for store_a. The address
    # belongs to the main customer, so the address-ownership check fires first.
    # A separate test below covers the pure cart_not_found case.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_a"],
                "service_id": seed["grocery_service_id"],
                "payment_method": "cash",
            },
        )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "invalid_address"


async def test_place_order_invalid_address_missing(
    as_customer: Any, seed: dict[str, int]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": 9999,
                "store_id": seed["store_a"],
                "service_id": seed["grocery_service_id"],
                "payment_method": "upi",
            },
        )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "invalid_address"


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
                "service_id": seed["grocery_service_id"],
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


async def test_place_order_for_store_cash_method(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_b"],
                "service_id": seed["bakery_service_id"],
                "payment_method": "cash",
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["payment"]["method"] == "cash"
    assert body["payment"]["status"] == "pending"
    assert body["store_id"] == seed["store_b"]
    assert body["service_id"] == seed["bakery_service_id"]
    assert body["service_name"] == "Bread"


async def test_place_order_pure_cart_not_found(
    as_customer: Any, seed: dict[str, int]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": 999_999,
                "service_id": seed["grocery_service_id"],
                "payment_method": "upi",
            },
        )
    # Task 12 added _validate_service_active_for_store ahead of cart lookup;
    # a non-existent store has no SellerProfileService row, so this now 409s
    # service_unavailable before reaching the cart_not_found branch.
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["detail"] == "service_unavailable"
    assert detail["store_id"] == 999_999
    assert detail["service_id"] == seed["grocery_service_id"]


async def test_place_order_invalid_payment_method(
    as_customer: Any, seed: dict[str, int]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_a"],
                "service_id": seed["grocery_service_id"],
                "payment_method": "bitcoin",
            },
        )
    assert resp.status_code == 422


async def test_place_order_missing_store_id(
    as_customer: Any, seed: dict[str, int]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "service_id": seed["grocery_service_id"],
                "payment_method": "upi",
            },
        )
    assert resp.status_code == 422


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
                "service_id": seed["grocery_service_id"],
                "payment_method": "upi",
            },
        )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["detail"] == "store_unavailable"
    assert detail["store_id"] == seed["store_a"]


async def _place_orders(seed: dict[str, int]) -> list[int]:
    """Place one order per store in the seeded cart and return their ids in
    the order [store_a, store_b]. Mirrors the per-store contract."""
    order_ids: list[int] = []
    pairs = (
        (seed["store_a"], seed["grocery_service_id"]),
        (seed["store_b"], seed["bakery_service_id"]),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for store_id, service_id in pairs:
            resp = await ac.post(
                "/api/v1/orders",
                json={
                    "customer_address_id": seed["customer_address_id"],
                    "store_id": store_id,
                    "service_id": service_id,
                    "payment_method": "upi",
                },
            )
            assert resp.status_code == 201, resp.text
            order_ids.append(resp.json()["id"])
    return order_ids


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


async def test_from_date_filter(as_customer: Any, seed: dict[str, int]) -> None:
    # Regression: a bare YYYY-MM-DD from_date must bind as a datetime, not a
    # VARCHAR (asyncpg rejects `timestamptz >= varchar` with a 500).
    await _place_orders(seed)
    today = datetime.now(timezone.utc).date()
    tomorrow = (today + timedelta(days=1)).isoformat()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        included = await ac.get(f"/api/v1/orders?from_date={today.isoformat()}")
        excluded = await ac.get(f"/api/v1/orders?from_date={tomorrow}")
        bad = await ac.get("/api/v1/orders?from_date=not-a-date")
    assert included.status_code == 200, included.text
    assert len(included.json()["orders"]) == 2
    assert excluded.status_code == 200
    assert excluded.json()["orders"] == []
    assert bad.status_code == 400
    assert bad.json()["detail"] == "invalid_from_date"


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
        resp = await _deliver_with_otp(ac, target)
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment"]["status"] == "paid"
    assert resp.json()["payment"]["paid_at"] is not None


async def _get_order_store(order_id: int) -> int:
    """Peek an order's store_id from the test database (not the prod engine)."""
    from sqlmodel.ext.asyncio.session import AsyncSession as S

    from tests.conftest import test_engine
    async with S(test_engine) as s:
        store_id = (await s.exec(select(Order.store_id).where(Order.id == order_id))).first()
        assert store_id is not None
        return store_id


async def _order_id_for_store(order_ids: list[int], store_id: int) -> int:
    """Return the id of the order belonging to `store_id`. Pre-resolves all
    stores so the lookup is deterministic regardless of place_orders_from_cart's
    return order."""
    stores = [await _get_order_store(oid) for oid in order_ids]
    return next(oid for oid, s in zip(order_ids, stores, strict=True) if s == store_id)


async def _deliver_with_otp(ac: AsyncClient, order_id: int) -> Any:
    """Walk packed→dispatched, read the generated code from the test DB, deliver."""
    from sqlmodel.ext.asyncio.session import AsyncSession as S

    from tests.conftest import test_engine

    await ac.post(f"/api/v1/orders/{order_id}/transition", json={"to": "packed"})
    await ac.post(f"/api/v1/orders/{order_id}/transition", json={"to": "dispatched"})
    async with S(test_engine) as s:
        code = (
            await s.exec(
                select(Delivery.delivery_otp).where(Delivery.order_id == order_id)
            )
        ).first()
    assert code is not None
    return await ac.post(
        f"/api/v1/orders/{order_id}/transition",
        json={"to": "delivered", "otp": code},
    )


async def test_customer_cancels_pending(as_customer: Any, seed: dict[str, int], session: AsyncSession) -> None:
    order_ids = await _place_orders(seed)
    # Deterministically pick store_a's order so the restock assertion always fires.
    target = await _order_id_for_store(order_ids, seed["store_a"])
    pre_stock = (await session.exec(select(StoreInventory.stock).where(StoreInventory.id == seed["inv_a"]))).first()
    assert pre_stock is not None

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
    assert pre_stock is not None

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "dispatched"})

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Admin cancel on a non-Pending order now requires a reason (>=10 chars)
        # per the admin-supervisor spec.
        resp = await ac.post(
            f"/api/v1/orders/{target}/cancel",
            json={"reason": "customer support escalation"},
        )
    assert resp.status_code == 200
    # Cancel from non-Pending status must still restock; this branch wasn't
    # exercised by the customer-cancels-Pending test.
    post_stock = (await session.exec(select(StoreInventory.stock).where(StoreInventory.id == seed["inv_a"]))).first()
    assert post_stock == pre_stock + 2


# ----------------------------------------------------------------------
# Admin supervisor order actions: rewind / refund / address-override
# ----------------------------------------------------------------------
async def _advance_to_dispatched(target: int) -> None:
    """Helper: walk an order Pending -> Packed -> Dispatched as the seller."""
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "dispatched"})


async def test_admin_rewind_dispatched_to_packed(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])
    await _advance_to_dispatched(target)

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ok = await ac.post(
            f"/api/v1/admin/orders/{target}/rewind",
            json={"to_status": "packed", "reason": "delivery driver returned"},
        )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "packed"


async def test_admin_rewind_from_terminal_status_rejected(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    # Cancel (terminal) then try to rewind.
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(f"/api/v1/orders/{target}/cancel")

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        terminal = await ac.post(
            f"/api/v1/admin/orders/{target}/rewind",
            json={"to_status": "pending", "reason": "post-cancel rewind"},
        )
    assert terminal.status_code == 409
    assert terminal.json()["detail"]["code"] == "terminal_status"


async def test_admin_refund_rejects_unpaid_payment(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    # Cancel pending order: order moves to Cancelled but payment stays Pending
    # (only Paid -> Refunded auto-flips). Refund must reject.
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(f"/api/v1/orders/{target}/cancel")

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/v1/admin/orders/{target}/refund",
            json={"reason": "should reject on payment status"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "payment_not_refundable"


async def test_admin_refund_delivered_order_marks_payment_refunded(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    # Walk to delivered (transition_order_status flips payment.status to Paid).
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await _deliver_with_otp(ac, target)
        assert r.status_code == 200, r.text

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/v1/admin/orders/{target}/refund",
            json={"reason": "customer support refund request"},
        )
    assert resp.status_code == 200

    payment = (await session.exec(
        select(Payment).where(Payment.order_id == target)
    )).first()
    assert payment is not None
    assert payment.status == PaymentStatus.Refunded


async def test_admin_override_delivery_address_out_of_radius(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    # Provide a coordinate far outside any 5km radius from store_a (which
    # uses the default seeded MG-Road / Gurugram lat-lng).
    far_payload = make_address(
        address_line1="999 Mars Drive",
        latitude=12.9716,
        longitude=77.5946,  # Bangalore — well outside Gurugram radius
    )

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/v1/admin/orders/{target}/delivery-address",
            json={
                "address": far_payload,
                "reason": "customer relocated to wrong city",
            },
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "delivery_out_of_radius"


# ─── Order-event notifications ──────────────────────────────────────────────
# The web-push dispatch is patched to a no-op in conftest (`_patch_email_dispatch`),
# so these assert the persisted in-app notification row only.

async def _list_customer_notifications() -> list[dict[str, Any]]:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/notifications")
    assert resp.status_code == 200, resp.text
    return resp.json()["notifications"]


async def test_placing_order_creates_pending_notification(
    as_customer: Any, seed: dict[str, int]
) -> None:
    await _place_orders(seed)
    items = await _list_customer_notifications()
    assert any(n["status_value"] == "pending" for n in items)
    assert any("placed" in n["title"].lower() for n in items)


async def test_transition_creates_packed_notification(
    as_customer: Any, seed: dict[str, int]
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
        assert r.status_code == 200, r.text

    items = await _list_customer_notifications()
    assert any(
        n["status_value"] == "packed" and "packed" in n["title"].lower() for n in items
    )


async def test_admin_cancel_creates_cancelled_notification(
    as_customer: Any, seed: dict[str, int]
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(
            f"/api/v1/orders/{target}/cancel", json={"reason": "out of stock, sorry"}
        )
        assert r.status_code == 200, r.text

    items = await _list_customer_notifications()
    assert any(n["status_value"] == "cancelled" for n in items)


async def test_admin_rewind_does_not_create_notification(
    as_customer: Any, seed: dict[str, int]
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        rp = await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
        assert rp.status_code == 200, rp.text

    before = len(await _list_customer_notifications())

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        rr = await ac.post(
            f"/api/v1/admin/orders/{target}/rewind",
            json={"to_status": "pending", "reason": "fix address issue"},
        )
        assert rr.status_code == 200, rr.text

    after = len(await _list_customer_notifications())
    assert after == before


# ─── Admin search / sort / pagination (Task 2) ──────────────────────────────


async def test_admin_orders_pagination_envelope(
    as_customer: Any, seed: dict[str, int]
) -> None:
    await _place_orders(seed)  # seeds 2 orders
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/orders?page=1&page_size=1")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {"orders", "total", "page", "page_size"}
    assert body["page"] == 1
    assert body["page_size"] == 1
    assert body["total"] >= 2
    assert len(body["orders"]) == 1


async def test_admin_orders_search_by_store_name(
    as_customer: Any, seed: dict[str, int]
) -> None:
    await _place_orders(seed)
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        full = await ac.get("/api/v1/orders")
        store_name = full.json()["orders"][0]["store_name"]
        term = store_name[:4]
        resp = await ac.get(f"/api/v1/orders?q={term}")
    assert resp.status_code == 200
    orders = resp.json()["orders"]
    assert orders
    assert all(term.lower() in o["store_name"].lower() for o in orders)


async def test_admin_orders_search_by_order_id(
    as_customer: Any, seed: dict[str, int]
) -> None:
    order_ids = await _place_orders(seed)
    target = order_ids[0]
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/orders?q=%23{target}")
    assert resp.status_code == 200
    ids = [o["id"] for o in resp.json()["orders"]]
    assert target in ids


async def test_admin_orders_status_delivered_filter(
    as_customer: Any, seed: dict[str, int]
) -> None:
    await _place_orders(seed)  # both Pending
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        delivered = await ac.get("/api/v1/orders?status=delivered")
        all_orders = await ac.get("/api/v1/orders?status=all")
    assert delivered.status_code == 200
    assert delivered.json()["orders"] == []
    assert all_orders.status_code == 200
    assert len(all_orders.json()["orders"]) >= 2


async def test_admin_orders_sort_total_desc(
    as_customer: Any, seed: dict[str, int]
) -> None:
    await _place_orders(seed)
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/orders?sort=total_desc")
    assert resp.status_code == 200
    totals = [o["total"] for o in resp.json()["orders"]]
    assert totals == sorted(totals, reverse=True)


async def test_admin_orders_search_oversized_numeric_q_no_500(
    as_customer: Any, seed: dict[str, int]
) -> None:
    """A digit string past the int32 ceiling must not 500 (asyncpg DataError)."""
    await _place_orders(seed)
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/orders?q=99999999999999")
    assert resp.status_code == 200
    assert resp.json()["orders"] == []


async def test_order_model_accepts_preferred_window(
    seed: dict[str, int], session: AsyncSession
) -> None:
    order = Order(
        customer_profile_id=seed["customer_profile"],
        store_id=seed["store_a"],
        service_id=seed["grocery_service_id"],
        service_name_snapshot="Apple",
        delivery_address_id=seed["customer_address_id"],
        delivery_address_snapshot="x",
        subtotal=1.0, delivery_fee=0.0, tax=0.0, total=1.0,
        preferred_delivery_date=date(2026, 6, 21),
        preferred_delivery_window="evening",
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    assert order.preferred_delivery_date == date(2026, 6, 21)
    assert order.preferred_delivery_window == "evening"


async def test_place_order_with_preferred_window_persists_and_returns(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    from app.utils.delivery_window import ist_today

    target = (ist_today() + timedelta(days=1)).isoformat()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_a"],
                "service_id": seed["grocery_service_id"],
                "payment_method": "upi",
                "preferred_delivery_date": target,
                "preferred_delivery_window": "evening",
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["preferred_delivery_date"] == target
    assert body["preferred_delivery_window"] == "evening"

    session.expire_all()
    order = (await session.exec(select(Order))).first()
    assert order is not None
    assert order.preferred_delivery_window == "evening"
    assert order.preferred_delivery_date.isoformat() == target


async def test_place_order_without_preferred_window_is_null(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_a"],
                "service_id": seed["grocery_service_id"],
                "payment_method": "upi",
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["preferred_delivery_date"] is None
    assert body["preferred_delivery_window"] is None


async def test_place_order_rejects_past_preferred_date(
    as_customer: Any, seed: dict[str, int]
) -> None:
    from app.utils.delivery_window import ist_today

    past = (ist_today() - timedelta(days=1)).isoformat()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_a"],
                "service_id": seed["grocery_service_id"],
                "payment_method": "upi",
                "preferred_delivery_date": past,
                "preferred_delivery_window": "morning",
            },
        )
    assert resp.status_code == 422, resp.text


async def test_pending_notification_body_includes_preferred_window(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    from app.models.notification import Notification
    from app.utils.delivery_window import ist_today

    target = (ist_today() + timedelta(days=1)).isoformat()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_a"],
                "service_id": seed["grocery_service_id"],
                "payment_method": "upi",
                "preferred_delivery_date": target,
                "preferred_delivery_window": "evening",
            },
        )
    assert resp.status_code == 201, resp.text
    session.expire_all()
    notif = (
        await session.exec(
            select(Notification).where(
                Notification.customer_profile_id == seed["customer_profile"]
            )
        )
    ).first()
    assert notif is not None
    assert "Requested delivery" in notif.body
    assert "Evening (3–9 PM)" in notif.body
