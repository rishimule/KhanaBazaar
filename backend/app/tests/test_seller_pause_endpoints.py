# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_seller, get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Service, ServiceTranslation
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from app.models.store import Store
from tests._helpers import make_address

mock_seller = User(id=7401, email="pause-seller@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture(autouse=True)
async def seed_seller_store(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    session.add(User(**mock_seller.model_dump()))
    await session.flush()
    addr = Address(**make_address())
    session.add(addr)
    await session.flush()
    profile = SellerProfile(
        user_id=mock_seller.id,
        first_name="Pause",
        business_name="Pause Store",
        phone="+919811117401",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(profile)
    await session.flush()
    svc = Service(slug="grocery-pause")
    session.add(svc)
    await session.flush()
    session.add(ServiceTranslation(service_id=svc.id, language_code="en", name="Grocery"))
    session.add(SellerProfileService(seller_profile_id=profile.id, service_id=svc.id))
    store_addr = Address(**make_address())
    session.add(store_addr)
    await session.flush()
    store = Store(name="Pause Store", seller_profile_id=profile.id, address_id=store_addr.id)
    session.add(store)
    await session.commit()
    yield {"service_id": svc.id, "store_id": store.id}


@pytest.fixture
def override_as_seller() -> Iterator[None]:
    app.dependency_overrides[get_current_seller] = lambda: mock_seller
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    yield None
    app.dependency_overrides.pop(get_current_seller, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_seller_pauses_own_store(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.patch(
            "/api/v1/sellers/me/store/pause",
            json={"is_paused": True, "reason": "Diwali", "paused_until": None},
        )
        assert r.status_code == 200, r.text
        assert r.json()["is_paused"] is True
        assert r.json()["pause_reason"] == "Diwali"


@pytest.mark.asyncio
async def test_seller_unpause_clears_fields(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.patch(
            "/api/v1/sellers/me/store/pause",
            json={"is_paused": True, "reason": "Diwali"},
        )
        r = await ac.patch("/api/v1/sellers/me/store/pause", json={"is_paused": False})
        assert r.status_code == 200, r.text
        assert r.json()["is_paused"] is False
        assert r.json()["pause_reason"] is None


@pytest.mark.asyncio
async def test_seller_pauses_service(override_as_seller: Any, seed_seller_store: dict) -> None:
    sid = seed_seller_store["service_id"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.patch(
            f"/api/v1/sellers/me/services/{sid}/pause",
            json={"is_paused": True, "reason": "No pharmacist"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["is_paused"] is True


@pytest.mark.asyncio
async def test_pause_rejects_past_date(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.patch(
            "/api/v1/sellers/me/store/pause",
            json={"is_paused": True, "paused_until": "2000-01-01"},
        )
        assert r.status_code == 422
