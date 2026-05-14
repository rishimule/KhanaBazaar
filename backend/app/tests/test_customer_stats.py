# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_customer
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Service
from app.models.commerce import Order, OrderStatus
from app.models.profile import CustomerProfile, SellerProfile, VerificationStatus
from app.models.store import Store

pytestmark = pytest.mark.asyncio


async def _make_address(session: AsyncSession) -> Address:
    addr = Address(
        address_line1="1 Test St",
        city="Pune",
        state="MH",
        pincode="411001",
        country="IN",
    )
    session.add(addr)
    await session.flush()
    return addr


class _Ids:
    def __init__(self, **kwargs: int | str) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


async def _make_customer(session: AsyncSession, email: str = "c@example.com") -> _Ids:
    user = User(email=email, role=UserRole.Customer, is_active=True)
    session.add(user)
    await session.flush()
    assert user.id is not None
    profile = CustomerProfile(user_id=user.id, first_name="Test")
    session.add(profile)
    await session.flush()
    assert profile.id is not None
    return _Ids(user_id=user.id, profile_id=profile.id, email=email)


def _user_for_override(ids: _Ids) -> User:
    return User(
        id=ids.user_id,  # type: ignore[attr-defined]
        email=ids.email,  # type: ignore[attr-defined]
        role=UserRole.Customer,
        is_active=True,
    )


async def _make_store(session: AsyncSession, name: str) -> _Ids:
    seller_user = User(
        email=f"seller-{name.lower().replace(' ', '-')}@example.com",
        role=UserRole.Seller,
        is_active=True,
    )
    session.add(seller_user)
    await session.flush()
    assert seller_user.id is not None
    biz_addr = await _make_address(session)
    assert biz_addr.id is not None
    seller_profile = SellerProfile(
        user_id=seller_user.id,
        first_name="Seller",
        phone=f"+91999{seller_user.id:07d}",
        business_name=f"{name} Co",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz_addr.id,
    )
    session.add(seller_profile)
    await session.flush()
    assert seller_profile.id is not None
    store_addr = await _make_address(session)
    assert store_addr.id is not None
    store = Store(
        name=name,
        is_active=True,
        seller_profile_id=seller_profile.id,
        address_id=store_addr.id,
        delivery_radius_km=5.0,
        pin_confirmed=True,
    )
    session.add(store)
    await session.flush()
    assert store.id is not None
    return _Ids(id=store.id, name=name)


async def _make_service(session: AsyncSession, slug: str = "grocery") -> _Ids:
    svc = Service(slug=slug, is_active=True, sort_order=0)
    session.add(svc)
    await session.flush()
    assert svc.id is not None
    return _Ids(id=svc.id, slug=slug)


async def _make_order(
    session: AsyncSession,
    *,
    profile_id: int,
    store_id: int,
    service: _Ids,
    total: float,
    placed_at: datetime,
    status: OrderStatus = OrderStatus.Delivered,
) -> None:
    addr = await _make_address(session)
    assert addr.id is not None
    order = Order(
        customer_profile_id=profile_id,
        store_id=store_id,
        service_id=service.id,  # type: ignore[attr-defined]
        service_name_snapshot=service.slug,  # type: ignore[attr-defined]
        delivery_address_id=addr.id,
        status=status,
        subtotal=total,
        delivery_fee=0,
        tax=0,
        total=total,
        delivery_address_snapshot="1 Test St",
        placed_at=placed_at,
    )
    session.add(order)
    await session.commit()


async def test_stats_empty(client: AsyncClient, session: AsyncSession):
    ids = await _make_customer(session)
    await session.commit()
    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(ids)
    try:
        r = await client.get("/api/v1/customers/me/stats")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["orders_this_month"] == 0
    assert data["lifetime_spend"] == 0
    assert data["favorite_store_id"] is None
    assert data["favorite_store_name"] is None
    assert data["recent_delivered"] == []


async def test_stats_aggregates(client: AsyncClient, session: AsyncSession):
    ids = await _make_customer(session)
    service = await _make_service(session)
    store_a = await _make_store(session, "Store A")
    store_b = await _make_store(session, "Store B")
    await session.commit()

    now = datetime.now(timezone.utc)
    for i in range(3):
        await _make_order(
            session,
            profile_id=ids.profile_id,  # type: ignore[attr-defined]
            store_id=store_a.id,  # type: ignore[attr-defined]
            service=service,
            total=500,
            placed_at=now - timedelta(days=i),
        )
    await _make_order(
        session,
        profile_id=ids.profile_id,  # type: ignore[attr-defined]
        store_id=store_b.id,  # type: ignore[attr-defined]
        service=service,
        total=200,
        placed_at=now - timedelta(days=2),
    )
    await _make_order(
        session,
        profile_id=ids.profile_id,  # type: ignore[attr-defined]
        store_id=store_b.id,  # type: ignore[attr-defined]
        service=service,
        total=100,
        placed_at=now - timedelta(days=70),
    )

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(ids)
    try:
        r = await client.get("/api/v1/customers/me/stats")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["orders_this_month"] == 4
    assert data["lifetime_spend"] == 1800
    assert data["favorite_store_id"] == store_a.id  # type: ignore[attr-defined]
    assert data["favorite_store_name"] == "Store A"
    assert len(data["recent_delivered"]) == 3
    assert data["recent_delivered"][0]["total"] == 500
    assert data["recent_delivered"][0]["store_name"] == "Store A"
