# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Tests that POST /api/v1/orders/ rejects out-of-radius delivery addresses
via the new PostGIS serviceability check in app.services.checkout."""
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Service
from app.models.commerce import Cart, CartItem
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory


async def _seed(
    session: AsyncSession, *,
    customer_lat: float, customer_lng: float,
    store_lat: float, store_lng: float,
    radius_km: float,
) -> dict[str, Any]:
    customer_user = User(
        id=701, email="cust@kb.com", role=UserRole.Customer, is_active=True,
    )
    seller_user = User(
        id=702, email="sel@kb.com", role=UserRole.Seller, is_active=True,
    )
    session.add_all([customer_user, seller_user])
    await session.flush()

    customer_profile = CustomerProfile(user_id=customer_user.id, first_name="C")
    session.add(customer_profile)
    await session.flush()

    cust_addr = Address(
        address_line1="C", city="Mumbai", state="Maharashtra",
        pincode="400001", country="India",
        latitude=customer_lat, longitude=customer_lng,
    )
    session.add(cust_addr)
    await session.flush()
    cust_address_link = CustomerAddress(
        customer_profile_id=customer_profile.id, address_id=cust_addr.id,
        is_default=True,
    )
    session.add(cust_address_link)
    await session.flush()

    seller_biz_addr = Address(
        address_line1="Biz", city="Mumbai", state="Maharashtra",
        pincode="400002", country="India",
        latitude=store_lat, longitude=store_lng,
    )
    session.add(seller_biz_addr)
    await session.flush()
    seller_profile = SellerProfile(
        user_id=seller_user.id, first_name="S", business_name="S",
        phone="+919811119999",
        bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_biz_addr.id,
    )
    session.add(seller_profile)
    await session.flush()

    store_addr = Address(
        address_line1="Store", city="Mumbai", state="Maharashtra",
        pincode="400003", country="India",
        latitude=store_lat, longitude=store_lng,
    )
    session.add(store_addr)
    await session.flush()
    store = Store(
        name="Test Store", seller_profile_id=seller_profile.id,
        address_id=store_addr.id, delivery_radius_km=radius_km,
        is_active=True, pin_confirmed=True,
    )
    session.add(store)
    await session.flush()

    from tests.test_carts import _seed_product
    product = await _seed_product(
        session, service_slug="grocery", category_slug="food",
        subcategory_slug="fruit", product_slug="apple",
        name="Apple", base_price=50.0,
    )
    grocery = (
        await session.exec(select(Service).where(Service.slug == "grocery"))
    ).first()
    assert grocery is not None
    session.add(SellerProfileService(
        seller_profile_id=seller_profile.id, service_id=grocery.id,
    ))
    await session.flush()

    inv = StoreInventory(
        store_id=store.id, product_id=product.id, price=50.0, stock=10,
    )
    session.add(inv)
    await session.flush()

    cart = Cart(customer_profile_id=customer_profile.id, store_id=store.id)
    session.add(cart)
    await session.flush()
    session.add(CartItem(cart_id=cart.id, inventory_id=inv.id, quantity=1))
    # Capture IDs BEFORE commit — commit expires ORM instances and re-access
    # would trigger sync IO outside the greenlet context.
    out = {
        "customer_user_id": customer_user.id,
        "customer_address_id": cust_address_link.id,
        "store_id": store.id,
    }
    await session.commit()
    return out


def _override_as(user_id: int) -> Any:
    user = User(
        id=user_id, email="cust@kb.com",
        role=UserRole.Customer, is_active=True,
    )
    return lambda: user


@pytest.mark.asyncio
async def test_order_succeeds_when_address_inside_radius(
    session: AsyncSession,
) -> None:
    seed = await _seed(
        session,
        customer_lat=18.9220, customer_lng=72.8347,
        store_lat=18.9220, store_lng=72.8347,
        radius_km=5.0,
    )
    app.dependency_overrides[get_current_user] = _override_as(
        seed["customer_user_id"]
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.post(
                "/api/v1/orders",
                json={
                    "customer_address_id": seed["customer_address_id"],
                    "store_id": seed["store_id"],
                    "payment_method": "upi",
                },
            )
        assert r.status_code in (200, 201), r.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_order_rejected_when_address_outside_radius(
    session: AsyncSession,
) -> None:
    seed = await _seed(
        session,
        customer_lat=19.1197, customer_lng=72.8470,  # Andheri-ish
        store_lat=18.9220, store_lng=72.8347,         # Gateway of India
        radius_km=2.0,
    )
    app.dependency_overrides[get_current_user] = _override_as(
        seed["customer_user_id"]
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.post(
                "/api/v1/orders",
                json={
                    "customer_address_id": seed["customer_address_id"],
                    "store_id": seed["store_id"],
                    "payment_method": "upi",
                },
            )
        assert r.status_code == 422
        assert "outside" in r.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
