# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Tests for /api/v1/geo/* endpoints.

Mocks the in-router calls to GoogleMapsClient/autocomplete/place_details/
reverse_geocode so we never touch the real Google API. Serviceability uses
real PostGIS in the test DB.
"""
from typing import Any, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.api import geo as geo_router
from app.core.config import settings
from app.core.google_maps import GeocodeNotFoundError, Place, Prediction
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import SellerProfile, VerificationStatus
from app.models.store import Store


class _StubClient:
    async def aclose(self) -> None: ...


@pytest.fixture(autouse=True)
def patched_geo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub out the Google client so the proxy returns canned data."""
    monkeypatch.setattr(geo_router, "_get_client", lambda: _StubClient())

    async def _stub_autocomplete(
        client: Any, *, query: str, session_token: str,
    ) -> list[Prediction]:
        return [Prediction(place_id="p1", description=f"{query}, India")]

    async def _stub_place_details(
        client: Any, *, place_id: str, session_token: str,
    ) -> Place:
        return Place(
            place_id=place_id,
            formatted_address="X Address",
            latitude=18.9220, longitude=72.8347,
            components=(),
        )

    async def _stub_reverse(client: Any, *, lat: float, lng: float) -> Place:
        return Place(
            place_id="p2",
            formatted_address="Reverse Address",
            latitude=lat, longitude=lng,
            components=(),
        )

    async def _stub_forward(client: Any, *, address: str) -> Place:
        if "nowhere" in address.lower():
            raise GeocodeNotFoundError(f"no geocode for {address!r}")
        return Place(
            place_id="p3",
            formatted_address=f"{address}, India",
            latitude=19.0760, longitude=72.8777,
            components=(),
        )

    monkeypatch.setattr(geo_router, "autocomplete", _stub_autocomplete)
    monkeypatch.setattr(geo_router, "place_details", _stub_place_details)
    monkeypatch.setattr(geo_router, "reverse_geocode", _stub_reverse)
    monkeypatch.setattr(geo_router, "forward_geocode", _stub_forward)
    # Server key must be present for _get_client check to pass
    monkeypatch.setattr(settings, "GOOGLE_MAPS_SERVER_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def reset_redis_state(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Disable Redis cache during tests + override the rate-limit dep.

    The rate-limit function is wired in via `Depends(_geo_rate_limit)` which
    captures the original callable at route-registration time, so a plain
    monkeypatch of the module attribute does NOT replace it. Use FastAPI's
    dependency_overrides for that one.
    """
    async def _no_cache_get(key: str) -> None:
        return None
    async def _no_cache_set(key: str, value: dict[str, Any], ttl: int) -> None:
        return None
    monkeypatch.setattr(geo_router, "_cache_get", _no_cache_get)
    monkeypatch.setattr(geo_router, "_cache_set", _no_cache_set)
    app.dependency_overrides[geo_router._geo_rate_limit] = lambda: None
    yield
    app.dependency_overrides.pop(geo_router._geo_rate_limit, None)


@pytest.mark.asyncio
async def test_autocomplete_returns_predictions() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get(
            "/api/v1/geo/autocomplete",
            params={"q": "andheri", "session_token": "s1"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["predictions"][0]["place_id"] == "p1"


@pytest.mark.asyncio
async def test_place_details_returns_lat_lng() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get(
            "/api/v1/geo/place/p1", params={"session_token": "s1"}
        )
    assert r.status_code == 200
    body = r.json()
    assert body["latitude"] == 18.9220
    assert body["longitude"] == 72.8347


@pytest.mark.asyncio
async def test_geocode_returns_lat_lng_for_known_address() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get(
            "/api/v1/geo/geocode",
            params={"address": "1 Marine Drive, Mumbai, Maharashtra, 400020"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["latitude"] == 19.0760
    assert body["longitude"] == 72.8777
    assert body["place_id"] == "p3"


@pytest.mark.asyncio
async def test_geocode_returns_404_when_not_found() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get(
            "/api/v1/geo/geocode",
            params={"address": "Somewhere in nowhere land"},
        )
    assert r.status_code == 404
    assert r.json()["detail"] == "address not found"


@pytest.mark.asyncio
async def test_reverse_returns_formatted_address() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get(
            "/api/v1/geo/reverse", params={"lat": 18.9, "lng": 72.8}
        )
    assert r.status_code == 200
    body = r.json()
    assert body["formatted_address"] == "Reverse Address"


@pytest.mark.asyncio
async def test_serviceability_global_no_stores_returns_zero(
    session: AsyncSession,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/api/v1/geo/serviceability",
            json={"lat": 18.9, "lng": 72.8},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["serviceable"] is False
    assert body["store_count"] == 0


@pytest.mark.asyncio
async def test_serviceability_per_store_true_when_inside_radius(
    session: AsyncSession,
) -> None:
    user = User(email="s@kb.com", role=UserRole.Seller, is_active=True)
    session.add(user)
    await session.flush()

    addr = Address(
        address_line1="x", city="Mumbai", state="Maharashtra",
        pincode="400001", country="India",
        latitude=18.9220, longitude=72.8347,
    )
    session.add(addr)
    await session.flush()
    profile = SellerProfile(
        user_id=user.id, first_name="A", business_name="B",
        phone="+919811110000", gst_number="G", fssai_license="F",
        bank_account_number="ACC", bank_ifsc="IFSC",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(profile)
    await session.flush()
    store = Store(
        name="Test Store", seller_profile_id=profile.id,
        address_id=addr.id, delivery_radius_km=5.0,
        is_active=True, pin_confirmed=True,
    )
    session.add(store)
    await session.commit()
    await session.refresh(store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Same point as store
        r = await ac.post(
            "/api/v1/geo/serviceability",
            json={"lat": 18.9220, "lng": 72.8347, "store_id": store.id},
        )
    assert r.status_code == 200
    assert r.json() == {"serviceable": True, "store_count": None}


@pytest.mark.asyncio
async def test_serviceability_per_store_false_when_outside_radius(
    session: AsyncSession,
) -> None:
    user = User(email="s@kb.com", role=UserRole.Seller, is_active=True)
    session.add(user)
    await session.flush()
    addr = Address(
        address_line1="x", city="Mumbai", state="Maharashtra",
        pincode="400001", country="India",
        latitude=18.9220, longitude=72.8347,
    )
    session.add(addr)
    await session.flush()
    profile = SellerProfile(
        user_id=user.id, first_name="A", business_name="B",
        phone="+919811110000", gst_number="G", fssai_license="F",
        bank_account_number="ACC", bank_ifsc="IFSC",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(profile)
    await session.flush()
    store = Store(
        name="Test Store", seller_profile_id=profile.id,
        address_id=addr.id, delivery_radius_km=2.0,  # 2 km
        is_active=True, pin_confirmed=True,
    )
    session.add(store)
    await session.commit()
    await session.refresh(store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # ~17 km away (Andheri-ish)
        r = await ac.post(
            "/api/v1/geo/serviceability",
            json={"lat": 19.1197, "lng": 72.8470, "store_id": store.id},
        )
    assert r.status_code == 200
    assert r.json()["serviceable"] is False


@pytest.mark.asyncio
async def test_serviceability_unknown_store_returns_false() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/api/v1/geo/serviceability",
            json={"lat": 18.9, "lng": 72.8, "store_id": 99999},
        )
    assert r.status_code == 200
    assert r.json()["serviceable"] is False


@pytest.mark.asyncio
async def test_rate_limit_returns_429_after_exceeding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real rate-limit logic by removing the override + patching
    the limit threshold low. Hits a fake IP via httpx headers so each test
    starts fresh in a function-scoped Redis namespace."""
    # Remove the no-op override installed by the autouse fixture.
    app.dependency_overrides.pop(geo_router._geo_rate_limit, None)
    monkeypatch.setattr(settings, "GEO_RATE_LIMIT_PER_MIN", 2)

    # Use a unique IP so the bucket starts at 0 even if other tests bumped it.
    headers = {"X-Forwarded-For": "10.10.10.99"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Note: starlette TestClient uses request.client.host for IP,
        # which doesn't read X-Forwarded-For by default. Skip the IP-spoof
        # and rely on a unique session_token namespace plus a low limit.
        for i in range(2):
            r = await ac.get(
                "/api/v1/geo/autocomplete",
                params={"q": f"x{i}", "session_token": "rl-token"},
                headers=headers,
            )
            assert r.status_code == 200, f"call {i} should succeed"
        r = await ac.get(
            "/api/v1/geo/autocomplete",
            params={"q": "x3", "session_token": "rl-token"},
            headers=headers,
        )
    assert r.status_code == 429
    # Cleanup the bucket key so other tests aren't affected.
    from app.core.redis import get_redis
    redis = await get_redis()
    await redis.delete("rl:geo:testclient")
