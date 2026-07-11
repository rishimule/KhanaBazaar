# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Service, ServiceTranslation
from app.models.profile import (
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store
from tests._helpers import make_address

mock_seller = User(id=762, email="pks-seller@kb.com", role=UserRole.Seller, is_active=True)
mock_admin = User(id=763, email="pks-admin@kb.com", role=UserRole.Admin, is_active=True)


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    for u in (mock_seller, mock_admin):
        session.add(User(**u.model_dump()))
    await session.flush()

    seller_addr = Address(**make_address(pincode="560301"))
    session.add(seller_addr)
    await session.flush()
    seller = SellerProfile(
        user_id=mock_seller.id, first_name="S", phone="+919811000762",
        business_name="Shop", bank_account_number="2", bank_ifsc="HDFC0000002",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_addr.id,
    )
    session.add(seller)
    await session.flush()

    store_addr = Address(**make_address(pincode="560302"))
    session.add(store_addr)
    await session.flush()
    store = Store(name="Shop", seller_profile_id=seller.id, address_id=store_addr.id)
    session.add(store)
    await session.flush()

    grocery = Service(slug="grocery")
    session.add(grocery)
    await session.flush()
    session.add(ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"))
    sps = SellerProfileService(seller_profile_id=seller.id, service_id=grocery.id)
    session.add(sps)
    await session.flush()

    ids = {
        "store_id": store.id, "service_id": grocery.id,
        "seller_id": seller.id, "sps_id": sps.id,
    }
    await session.commit()
    yield ids  # type: ignore[misc]


@pytest.fixture
def staff_client_factory():  # noqa: ANN201
    @asynccontextmanager
    async def _make(user: User):  # noqa: ANN202
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    return _make


async def test_signup_seller_sets_pickup(
    staff_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    seller = (await session.exec(
        select(SellerProfile).where(SellerProfile.id == seed["seller_id"])
    )).first()
    seller.verification_status = VerificationStatus.Pending
    await session.commit()
    async with staff_client_factory(mock_seller) as ac:
        resp = await ac.patch(f"/api/v1/sellers/me/services/{seed['service_id']}", json={
            "free_delivery_threshold": 0, "delivery_fee": 0, "pickup_enabled": True,
        })
    assert resp.status_code == 200, resp.text
    assert resp.json()["pickup_enabled"] is True
    sps = await session.get(SellerProfileService, seed["sps_id"])
    await session.refresh(sps)
    assert sps.pickup_enabled is True


async def test_admin_sets_pickup(
    staff_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    async with staff_client_factory(mock_admin) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{mock_seller.id}/services/{seed['service_id']}",
            json={"free_delivery_threshold": 0, "delivery_fee": 0, "pickup_enabled": True},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["pickup_enabled"] is True
    sps = await session.get(SellerProfileService, seed["sps_id"])
    await session.refresh(sps)
    assert sps.pickup_enabled is True


async def test_admin_hub_service_includes_pickup(
    staff_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    sps = await session.get(SellerProfileService, seed["sps_id"])
    sps.pickup_enabled = True
    await session.commit()
    async with staff_client_factory(mock_admin) as ac:
        resp = await ac.get(f"/api/v1/admin/sellers/{mock_seller.id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["services"][0]["pickup_enabled"] is True
