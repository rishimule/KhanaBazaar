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
from app.models.commerce import Order, OrderStatus
from app.models.profile import CustomerProfile, SellerProfile, VerificationStatus
from app.models.store import Store
from tests._helpers import make_address

_CUSTOMER = User(id=9210, email="sas-cust@kb.com", role=UserRole.Customer, is_active=True)
_SELLER = User(id=9211, email="sas-seller@kb.com", role=UserRole.Seller, is_active=True)
_OTHER_SELLER = User(
    id=9212, email="sas-other@kb.com", role=UserRole.Seller, is_active=True
)


async def _seed_two_sellers(session: AsyncSession) -> dict[str, int]:
    """Two approved sellers, each owning one store, plus a customer + service.

    Mirrors the store/seller half of the `seed` fixture in tests/test_orders.py.
    """
    for u in (_CUSTOMER, _SELLER, _OTHER_SELLER):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer_profile = CustomerProfile(user_id=_CUSTOMER.id, first_name="Cust")
    session.add(customer_profile)

    addrs = [Address(**make_address(pincode=f"5601{i:02d}")) for i in range(5)]
    session.add_all(addrs)
    await session.flush()

    seller_profile = SellerProfile(
        user_id=_SELLER.id,
        first_name="S1",
        phone="+919800009210",
        business_name="S1 Store",
        verification_status=VerificationStatus.Approved,
        business_address_id=addrs[0].id,
    )
    other_seller_profile = SellerProfile(
        user_id=_OTHER_SELLER.id,
        first_name="S2",
        phone="+919800009220",
        business_name="S2 Store",
        verification_status=VerificationStatus.Approved,
        business_address_id=addrs[1].id,
    )
    session.add_all([seller_profile, other_seller_profile])
    await session.flush()

    store = Store(
        name="Store A", seller_profile_id=seller_profile.id, address_id=addrs[2].id
    )
    other_store = Store(
        name="Store B",
        seller_profile_id=other_seller_profile.id,
        address_id=addrs[3].id,
    )
    session.add_all([store, other_store])
    await session.flush()

    from tests.test_carts import _seed_product

    _product, service_id = await _seed_product(
        session,
        service_slug="grocery",
        category_slug="food",
        subcategory_slug="fruit",
        product_slug="apple",
        name="Apple",
        base_price=50.0,
    )
    await session.flush()

    assert store.id is not None
    assert other_store.id is not None
    assert customer_profile.id is not None
    return {
        "store_id": store.id,
        "other_store_id": other_store.id,
        "customer_profile_id": customer_profile.id,
        "service_id": service_id,
        "delivery_address_id": addrs[4].id or 0,
    }


def _order(seed: dict[str, int], *, store_id: int, status: OrderStatus) -> Order:
    return Order(
        customer_profile_id=seed["customer_profile_id"],
        store_id=store_id,
        service_id=seed["service_id"],
        service_name_snapshot="Grocery",
        delivery_address_id=seed["delivery_address_id"],
        status=status,
        subtotal=100.0,
        delivery_fee=0.0,
        tax=0.0,
        total=100.0,
        delivery_address_snapshot="somewhere",
    )


@pytest.fixture
async def seller_client_seed(
    session: AsyncSession,
) -> AsyncGenerator[dict[str, int], None]:
    """Two pending + one delivered at this seller's store, one pending elsewhere."""
    seed = await _seed_two_sellers(session)
    pending_a = _order(seed, store_id=seed["store_id"], status=OrderStatus.Pending)
    pending_b = _order(seed, store_id=seed["store_id"], status=OrderStatus.Pending)
    delivered = _order(seed, store_id=seed["store_id"], status=OrderStatus.Delivered)
    elsewhere = _order(
        seed, store_id=seed["other_store_id"], status=OrderStatus.Pending
    )
    session.add_all([pending_a, pending_b, delivered, elsewhere])
    await session.flush()
    assert pending_a.id is not None and pending_b.id is not None
    seed["newest_pending_id"] = max(pending_a.id, pending_b.id)
    await session.commit()

    app.dependency_overrides[get_current_user] = lambda: _SELLER
    try:
        yield seed
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def seller_no_orders_seed(
    session: AsyncSession,
) -> AsyncGenerator[dict[str, int], None]:
    seed = await _seed_two_sellers(session)
    await session.commit()
    app.dependency_overrides[get_current_user] = lambda: _SELLER
    try:
        yield seed
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_summary_counts_only_pending_orders_of_this_seller(
    seller_client_seed: dict[str, int],
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/orders/seller/alert-summary")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pending_count"] == 2
    assert body["latest_pending_order_id"] == seller_client_seed["newest_pending_id"]
    assert body["latest_pending_at"] is not None


@pytest.mark.asyncio
async def test_other_seller_sees_only_their_own_pending_order(
    seller_client_seed: dict[str, int],
) -> None:
    """Tenant isolation from the other side: the second seller's single pending
    order at their own store must not be mixed with this seller's two."""
    app.dependency_overrides[get_current_user] = lambda: _OTHER_SELLER
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/orders/seller/alert-summary")
    assert res.status_code == 200, res.text
    assert res.json()["pending_count"] == 1


@pytest.mark.asyncio
async def test_admin_without_a_seller_profile_sees_no_orders(
    seller_client_seed: dict[str, int],
) -> None:
    """get_current_seller admits Admins; an admin owns no store, so the
    store-less early return must fire rather than leaking a platform-wide count."""
    admin = User(id=9213, email="sas-admin@kb.com", role=UserRole.Admin, is_active=True)
    app.dependency_overrides[get_current_user] = lambda: admin
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/orders/seller/alert-summary")
    assert res.status_code == 200, res.text
    assert res.json() == {
        "pending_count": 0,
        "latest_pending_order_id": None,
        "latest_pending_at": None,
    }


@pytest.mark.asyncio
async def test_customer_is_forbidden(seller_client_seed: dict[str, int]) -> None:
    customer = User(
        id=9214, email="sas-c2@kb.com", role=UserRole.Customer, is_active=True
    )
    app.dependency_overrides[get_current_user] = lambda: customer
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/orders/seller/alert-summary")
    assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_summary_is_zero_for_a_seller_with_no_pending_orders(
    seller_no_orders_seed: dict[str, int],
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/orders/seller/alert-summary")
    assert res.status_code == 200, res.text
    assert res.json() == {
        "pending_count": 0,
        "latest_pending_order_id": None,
        "latest_pending_at": None,
    }
