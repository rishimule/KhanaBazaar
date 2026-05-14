# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_customer, get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Service
from app.models.commerce import (
    Delivery,
    DeliveryStatus,
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.profile import CustomerProfile, SellerProfile, VerificationStatus
from app.models.store import Store

pytestmark = pytest.mark.asyncio


class _Ids:
    def __init__(self, **kwargs: int | str) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


async def _seed(
    session: AsyncSession,
    *,
    status: OrderStatus = OrderStatus.Delivered,
    customer_email: str = "rev@example.com",
) -> _Ids:
    customer = User(email=customer_email, role=UserRole.Customer, is_active=True)
    session.add(customer)
    await session.flush()
    customer_id = customer.id
    assert customer_id is not None
    profile = CustomerProfile(user_id=customer_id, first_name="R")
    session.add(profile)
    await session.flush()
    profile_id = profile.id
    assert profile_id is not None

    seller_user = User(
        email=f"seller-{customer_id}@example.com", role=UserRole.Seller, is_active=True
    )
    session.add(seller_user)
    await session.flush()
    seller_user_id = seller_user.id
    biz_addr = Address(
        address_line1="1 Biz", city="X", state="MH", pincode="400001", country="IN"
    )
    session.add(biz_addr)
    await session.flush()
    biz_addr_id = biz_addr.id
    seller_profile = SellerProfile(
        user_id=seller_user_id,
        first_name="S",
        phone=f"+91999{customer_id:07d}",
        business_name="Biz",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz_addr_id,
    )
    session.add(seller_profile)
    await session.flush()
    seller_profile_id = seller_profile.id
    store_addr = Address(
        address_line1="1 Store", city="X", state="MH", pincode="400001", country="IN"
    )
    session.add(store_addr)
    await session.flush()
    store_addr_id = store_addr.id
    store = Store(
        name="Store",
        is_active=True,
        seller_profile_id=seller_profile_id,
        address_id=store_addr_id,
        delivery_radius_km=5.0,
        pin_confirmed=True,
    )
    session.add(store)
    await session.flush()
    store_id = store.id
    service = Service(slug="grocery", is_active=True, sort_order=0)
    session.add(service)
    await session.flush()
    service_id = service.id
    deliv_addr = Address(
        address_line1="1 Deliv", city="X", state="MH", pincode="400001", country="IN"
    )
    session.add(deliv_addr)
    await session.flush()
    deliv_addr_id = deliv_addr.id
    order = Order(
        customer_profile_id=profile_id,
        store_id=store_id,
        service_id=service_id,
        service_name_snapshot="grocery",
        delivery_address_id=deliv_addr_id,
        status=status,
        subtotal=100,
        delivery_fee=0,
        tax=0,
        total=100,
        delivery_address_snapshot="1 Deliv",
    )
    session.add(order)
    await session.flush()
    order_id = order.id
    assert order_id is not None
    payment = Payment(
        order_id=order_id,
        amount=100,
        method=PaymentMethod.Upi,
        status=PaymentStatus.Pending,
    )
    delivery = Delivery(
        order_id=order_id,
        status=DeliveryStatus.Delivered if status == OrderStatus.Delivered else DeliveryStatus.Pending,
        delivered_at=datetime.now(timezone.utc) if status == OrderStatus.Delivered else None,
    )
    session.add(payment)
    session.add(delivery)
    await session.commit()
    return _Ids(
        user_id=customer_id,
        email=customer_email,
        profile_id=profile_id,
        order_id=order_id,
    )


def _user_for(ids: _Ids) -> User:
    return User(
        id=ids.user_id,  # type: ignore[attr-defined]
        email=ids.email,  # type: ignore[attr-defined]
        role=UserRole.Customer,
        is_active=True,
    )


async def test_review_happy_path(client: AsyncClient, session: AsyncSession):
    ids = await _seed(session)
    app.dependency_overrides[get_current_customer] = lambda: _user_for(ids)
    app.dependency_overrides[get_current_user] = lambda: _user_for(ids)
    try:
        r = await client.post(
            f"/api/v1/orders/{ids.order_id}/review",  # type: ignore[attr-defined]
            json={"rating": 5, "comment": "Great!"},
        )
        assert r.status_code == 200, r.text
        r2 = await client.get(f"/api/v1/orders/{ids.order_id}")  # type: ignore[attr-defined]
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
        app.dependency_overrides.pop(get_current_user, None)
    assert r2.status_code == 200, r2.text
    assert r2.json()["review"]["rating"] == 5


async def test_review_rejects_not_delivered(client: AsyncClient, session: AsyncSession):
    ids = await _seed(session, status=OrderStatus.Pending, customer_email="np@example.com")
    app.dependency_overrides[get_current_customer] = lambda: _user_for(ids)
    try:
        r = await client.post(
            f"/api/v1/orders/{ids.order_id}/review",  # type: ignore[attr-defined]
            json={"rating": 5},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "order_not_delivered"


async def test_review_rejects_duplicate(client: AsyncClient, session: AsyncSession):
    ids = await _seed(session, customer_email="dup@example.com")
    app.dependency_overrides[get_current_customer] = lambda: _user_for(ids)
    try:
        await client.post(
            f"/api/v1/orders/{ids.order_id}/review",  # type: ignore[attr-defined]
            json={"rating": 5},
        )
        r = await client.post(
            f"/api/v1/orders/{ids.order_id}/review",  # type: ignore[attr-defined]
            json={"rating": 4},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "review_exists"


@pytest.mark.parametrize("bad", [0, 6, -1])
async def test_review_rejects_bad_rating(
    client: AsyncClient, session: AsyncSession, bad: int
):
    ids = await _seed(session, customer_email=f"bad{bad}@example.com")
    app.dependency_overrides[get_current_customer] = lambda: _user_for(ids)
    try:
        r = await client.post(
            f"/api/v1/orders/{ids.order_id}/review",  # type: ignore[attr-defined]
            json={"rating": bad},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 422


async def test_review_rejects_non_owner(client: AsyncClient, session: AsyncSession):
    owner_ids = await _seed(session, customer_email="owner@example.com")
    other = User(email="other@example.com", role=UserRole.Customer, is_active=True)
    session.add(other)
    await session.flush()
    other_user_id = other.id
    assert other_user_id is not None
    session.add(CustomerProfile(user_id=other_user_id, first_name="Other"))
    await session.commit()
    other_view = User(
        id=other_user_id,
        email="other@example.com",
        role=UserRole.Customer,
        is_active=True,
    )
    app.dependency_overrides[get_current_customer] = lambda: other_view
    try:
        r = await client.post(
            f"/api/v1/orders/{owner_ids.order_id}/review",  # type: ignore[attr-defined]
            json={"rating": 5},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 404
