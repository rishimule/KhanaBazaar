# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Tests for distance filter + sort on GET /api/v1/stores/."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import SellerProfile, VerificationStatus
from app.models.store import Store


async def _seed_store(
    session: AsyncSession, name: str, lat: float, lng: float,
    radius_km: float = 5.0,
) -> Store:
    user = User(
        email=f"{name.lower().replace(' ', '_')}@kb.com",
        role=UserRole.Seller, is_active=True,
    )
    session.add(user)
    await session.flush()
    addr = Address(
        address_line1="x", city="Mumbai", state="Maharashtra",
        pincode="400001", country="India",
        latitude=lat, longitude=lng,
    )
    session.add(addr)
    await session.flush()
    profile = SellerProfile(
        user_id=user.id, first_name=name, business_name=f"{name} Business",
        phone=f"+91981111{user.id:04d}",
        gst_number=f"G{user.id:020d}", fssai_license=f"F{user.id:013d}",
        bank_account_number=f"ACC{user.id}", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(profile)
    await session.flush()
    store = Store(
        name=name, seller_profile_id=profile.id, address_id=addr.id,
        delivery_radius_km=radius_km, is_active=True, pin_confirmed=True,
    )
    session.add(store)
    await session.flush()
    return store


@pytest.mark.asyncio
async def test_list_stores_no_lat_lng_returns_all_active_without_distance(
    session: AsyncSession,
) -> None:
    await _seed_store(session, "Near", 18.9400, 72.8360)
    await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get("/api/v1/stores/")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["distance_km"] is None


@pytest.mark.asyncio
async def test_list_stores_sorted_by_distance_excludes_far(
    session: AsyncSession,
) -> None:
    # Reference point ~ Mumbai CST.
    await _seed_store(session, "Near", 18.9400, 72.8360, radius_km=5.0)  # ~50m
    await _seed_store(session, "Mid", 18.9500, 72.8500, radius_km=5.0)   # ~2km
    await _seed_store(session, "Far", 19.0760, 72.8777, radius_km=5.0)   # ~17km
    await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get(
            "/api/v1/stores/",
            params={"lat": 18.9398, "lng": 72.8355, "sort": "distance"},
        )
    assert r.status_code == 200
    body = r.json()
    names = [s["name"] for s in body]
    # Far excluded by its 5km radius (~17km away). Near < Mid by distance.
    assert names == ["Near", "Mid"]
    assert body[0]["distance_km"] < body[1]["distance_km"]
    assert body[0]["distance_km"] >= 0


@pytest.mark.asyncio
async def test_list_stores_user_radius_cap_shrinks_radius(
    session: AsyncSession,
) -> None:
    await _seed_store(session, "Near", 18.9400, 72.8360, radius_km=5.0)
    await _seed_store(session, "Mid", 18.9500, 72.8500, radius_km=5.0)
    await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get(
            "/api/v1/stores/",
            params={
                "lat": 18.9398, "lng": 72.8355,
                "sort": "distance", "radius_km": 0.2,
            },
        )
    body = r.json()
    # Only "Near" (~50m) within 200m cap.
    assert [s["name"] for s in body] == ["Near"]


@pytest.mark.asyncio
async def test_list_stores_skips_stores_with_null_geo(
    session: AsyncSession,
) -> None:
    # Seed a store WITHOUT lat/lng; should be excluded from distance results.
    user = User(email="noloc@kb.com", role=UserRole.Seller, is_active=True)
    session.add(user)
    await session.flush()
    addr = Address(
        address_line1="x", city="Mumbai", state="Maharashtra",
        pincode="400001", country="India",
    )
    session.add(addr)
    await session.flush()
    profile = SellerProfile(
        user_id=user.id, first_name="N", business_name="N",
        phone="+919811119999", gst_number="GG", fssai_license="FF",
        bank_account_number="ACC", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(profile)
    await session.flush()
    session.add(Store(
        name="NoGeo", seller_profile_id=profile.id, address_id=addr.id,
        delivery_radius_km=5.0, is_active=True,
    ))
    await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get(
            "/api/v1/stores/",
            params={"lat": 18.9398, "lng": 72.8355},
        )
    assert r.status_code == 200
    assert r.json() == []
