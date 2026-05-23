# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_customer
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    MasterProduct,
    MasterProductTranslation,
    Service,
    Subcategory,
)
from app.models.commerce import Favorite
from app.models.profile import CustomerProfile, SellerProfile, VerificationStatus
from app.models.store import Store, StoreInventory

pytestmark = pytest.mark.asyncio


class _Ids:
    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


async def _make_address(
    session: AsyncSession,
    lat: float = 18.5204,
    lng: float = 73.8567,
) -> Address:
    addr = Address(
        address_line1="1 Test St",
        city="Pune",
        state="MH",
        pincode="411001",
        country="IN",
        latitude=lat,
        longitude=lng,
    )
    session.add(addr)
    await session.flush()
    return addr


async def _make_customer(
    session: AsyncSession, email: str = "c@example.com"
) -> _Ids:
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


async def _make_catalog(session: AsyncSession) -> _Ids:
    svc = Service(slug="grocery", is_active=True, sort_order=0)
    session.add(svc)
    await session.flush()
    assert svc.id is not None
    cat = Category(service_id=svc.id, slug="produce", sort_order=0, is_active=True)
    session.add(cat)
    await session.flush()
    assert cat.id is not None
    sub = Subcategory(
        category_id=cat.id, slug="fruit", sort_order=0, is_active=True
    )
    session.add(sub)
    await session.flush()
    assert sub.id is not None
    p1 = MasterProduct(
        subcategory_id=sub.id,
        slug="apple",
        image_url="https://example.test/apple.jpg",
        base_price=50.0,
        is_active=True,
    )
    p2 = MasterProduct(
        subcategory_id=sub.id,
        slug="banana",
        image_url="https://example.test/banana.jpg",
        base_price=40.0,
        is_active=True,
    )
    session.add_all([p1, p2])
    await session.flush()
    assert p1.id is not None
    assert p2.id is not None
    session.add_all([
        MasterProductTranslation(
            master_product_id=p1.id,
            language_code="en",
            name="Apple",
            description="Fresh apple",
        ),
        MasterProductTranslation(
            master_product_id=p2.id,
            language_code="en",
            name="Banana",
            description="Fresh banana",
        ),
    ])
    await session.flush()
    return _Ids(
        service_id=svc.id,
        category_id=cat.id,
        subcategory_id=sub.id,
        product_a_id=p1.id,
        product_b_id=p2.id,
    )


async def _make_store_with_loc(
    session: AsyncSession,
    name: str,
    lat: float,
    lng: float,
    delivery_radius_km: float = 5.0,
) -> _Ids:
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
        first_name="S",
        phone=f"+91999{seller_user.id:07d}",
        business_name=f"{name} Co",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz_addr.id,
    )
    session.add(seller_profile)
    await session.flush()
    assert seller_profile.id is not None
    store_addr = await _make_address(session, lat=lat, lng=lng)
    assert store_addr.id is not None
    store = Store(
        name=name,
        is_active=True,
        seller_profile_id=seller_profile.id,
        address_id=store_addr.id,
        delivery_radius_km=delivery_radius_km,
        pin_confirmed=True,
    )
    session.add(store)
    await session.flush()
    assert store.id is not None
    return _Ids(id=store.id, name=name)


async def _stock(
    session: AsyncSession,
    store_id: int,
    product_id: int,
    price: float = 50.0,
    stock: int = 10,
) -> int:
    inv = StoreInventory(
        store_id=store_id,
        product_id=product_id,
        price=price,
        stock=stock,
    )
    session.add(inv)
    await session.flush()
    assert inv.id is not None
    return int(inv.id)


async def test_toggle_add_is_idempotent(
    client: AsyncClient, session: AsyncSession
) -> None:
    cust = await _make_customer(session)
    cat = await _make_catalog(session)
    await session.commit()

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(cust)
    try:
        r1 = await client.post(f"/api/v1/favorites/{cat.product_a_id}")
        r2 = await client.post(f"/api/v1/favorites/{cat.product_a_id}")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)

    assert r1.status_code in (200, 201), r1.text
    assert r2.status_code in (200, 201), r2.text

    rows = (
        await session.exec(
            select(Favorite).where(Favorite.customer_profile_id == cust.profile_id)
        )
    ).all()
    assert len(list(rows)) == 1
    assert rows[0].product_id == cat.product_a_id


async def test_delete_is_idempotent(
    client: AsyncClient, session: AsyncSession
) -> None:
    cust = await _make_customer(session)
    cat = await _make_catalog(session)
    await session.commit()

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(cust)
    try:
        await client.post(f"/api/v1/favorites/{cat.product_a_id}")
        r1 = await client.delete(f"/api/v1/favorites/{cat.product_a_id}")
        r2 = await client.delete(f"/api/v1/favorites/{cat.product_a_id}")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)

    assert r1.status_code == 204
    assert r2.status_code == 204


async def test_add_unknown_product_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    cust = await _make_customer(session)
    await session.commit()

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(cust)
    try:
        r = await client.post("/api/v1/favorites/999999")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 404
    assert r.json()["detail"] == "product_not_found"


async def test_list_ids_empty_and_populated(
    client: AsyncClient, session: AsyncSession
) -> None:
    cust = await _make_customer(session)
    cat = await _make_catalog(session)
    await session.commit()

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(cust)
    try:
        r_empty = await client.get("/api/v1/favorites/ids")
        await client.post(f"/api/v1/favorites/{cat.product_a_id}")
        await client.post(f"/api/v1/favorites/{cat.product_b_id}")
        r_full = await client.get("/api/v1/favorites/ids")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)

    assert r_empty.json() == {"ids": []}
    assert sorted(r_full.json()["ids"]) == sorted(
        [cat.product_a_id, cat.product_b_id]
    )


async def test_grouped_serviceable_and_unavailable(
    client: AsyncClient, session: AsyncSession
) -> None:
    cust = await _make_customer(session)
    cat = await _make_catalog(session)
    near = await _make_store_with_loc(session, "Near Store", 18.5204, 73.8567)
    far = await _make_store_with_loc(session, "Far Store", 19.9975, 73.7898)
    await _stock(session, near.id, cat.product_a_id)
    await _stock(session, far.id, cat.product_b_id)
    await session.commit()

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(cust)
    try:
        await client.post(f"/api/v1/favorites/{cat.product_a_id}")
        await client.post(f"/api/v1/favorites/{cat.product_b_id}")
        r = await client.get(
            "/api/v1/favorites/", params={"lat": 18.5204, "lng": 73.8567}
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)

    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["groups"]) == 1
    g = body["groups"][0]
    assert g["store_id"] == near.id
    assert g["store_name"] == "Near Store"
    assert g["distance_km"] < 0.1
    assert [it["product_id"] for it in g["items"]] == [cat.product_a_id]
    assert g["items"][0]["service_id"] == cat.service_id
    assert g["items"][0]["service_name"] == "grocery"
    assert [p["product_id"] for p in body["unavailable"]] == [cat.product_b_id]


async def test_grouped_orders_by_recent_first(
    client: AsyncClient, session: AsyncSession
) -> None:
    cust = await _make_customer(session)
    cat = await _make_catalog(session)
    store = await _make_store_with_loc(session, "S", 18.5204, 73.8567)
    await _stock(session, store.id, cat.product_a_id)
    await _stock(session, store.id, cat.product_b_id)
    await session.commit()

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(cust)
    try:
        await client.post(f"/api/v1/favorites/{cat.product_a_id}")
        await client.post(f"/api/v1/favorites/{cat.product_b_id}")
        r = await client.get(
            "/api/v1/favorites/", params={"lat": 18.5204, "lng": 73.8567}
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)

    items = r.json()["groups"][0]["items"]
    assert [it["product_id"] for it in items] == [
        cat.product_b_id,
        cat.product_a_id,
    ]


async def test_grouped_no_favourites_returns_empty(
    client: AsyncClient, session: AsyncSession
) -> None:
    cust = await _make_customer(session)
    await session.commit()

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(cust)
    try:
        r = await client.get(
            "/api/v1/favorites/", params={"lat": 18.5204, "lng": 73.8567}
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)

    assert r.status_code == 200
    assert r.json() == {"groups": [], "unavailable": []}


async def test_store_favorites_endpoint_scoped(
    client: AsyncClient, session: AsyncSession
) -> None:
    cust = await _make_customer(session)
    cat = await _make_catalog(session)
    s1 = await _make_store_with_loc(session, "S1", 18.5204, 73.8567)
    s2 = await _make_store_with_loc(session, "S2", 18.5204, 73.8567)
    await _stock(session, s1.id, cat.product_a_id)
    await _stock(session, s2.id, cat.product_b_id)
    await session.commit()

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(cust)
    try:
        await client.post(f"/api/v1/favorites/{cat.product_a_id}")
        await client.post(f"/api/v1/favorites/{cat.product_b_id}")
        r = await client.get(f"/api/v1/favorites/stores/{s1.id}")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)

    items = r.json()
    assert [it["product_id"] for it in items] == [cat.product_a_id]


async def test_non_customer_forbidden(
    client: AsyncClient, session: AsyncSession
) -> None:
    def deny() -> None:
        raise HTTPException(status_code=403, detail="not_a_customer")

    app.dependency_overrides[get_current_customer] = deny
    try:
        r = await client.get("/api/v1/favorites/ids")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 403


async def test_add_inactive_product_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    cust = await _make_customer(session)
    cat = await _make_catalog(session)
    # Soft-deactivate product A.
    prod = await session.get(MasterProduct, cat.product_a_id)
    assert prod is not None
    prod.is_active = False
    session.add(prod)
    await session.commit()

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(cust)
    try:
        r = await client.post(f"/api/v1/favorites/{cat.product_a_id}")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 404


async def test_grouped_excludes_unavailable_inventory(
    client: AsyncClient, session: AsyncSession
) -> None:
    cust = await _make_customer(session)
    cat = await _make_catalog(session)
    store = await _make_store_with_loc(session, "Store", 18.5204, 73.8567)
    inv_id = await _stock(session, store.id, cat.product_a_id)
    inv = await session.get(StoreInventory, inv_id)
    assert inv is not None
    inv.is_available = False
    session.add(inv)
    await session.commit()

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(cust)
    try:
        await client.post(f"/api/v1/favorites/{cat.product_a_id}")
        r = await client.get(
            "/api/v1/favorites/", params={"lat": 18.5204, "lng": 73.8567}
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)

    body = r.json()
    assert body["groups"] == []
    assert [p["product_id"] for p in body["unavailable"]] == [cat.product_a_id]


async def test_grouped_excludes_zero_stock(
    client: AsyncClient, session: AsyncSession
) -> None:
    cust = await _make_customer(session)
    cat = await _make_catalog(session)
    store = await _make_store_with_loc(session, "Store", 18.5204, 73.8567)
    await _stock(session, store.id, cat.product_a_id, stock=0)
    await session.commit()

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(cust)
    try:
        await client.post(f"/api/v1/favorites/{cat.product_a_id}")
        r = await client.get(
            "/api/v1/favorites/", params={"lat": 18.5204, "lng": 73.8567}
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)

    body = r.json()
    assert body["groups"] == []
    assert [p["product_id"] for p in body["unavailable"]] == [cat.product_a_id]


async def test_cross_customer_isolation(
    client: AsyncClient, session: AsyncSession
) -> None:
    a = await _make_customer(session, email="a@example.com")
    b = await _make_customer(session, email="b@example.com")
    cat = await _make_catalog(session)
    await session.commit()

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(a)
    try:
        await client.post(f"/api/v1/favorites/{cat.product_a_id}")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)

    app.dependency_overrides[get_current_customer] = lambda: _user_for_override(b)
    try:
        r = await client.get("/api/v1/favorites/ids")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)

    assert r.json()["ids"] == []
