# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_user
from app.models.address import Address
from app.models.admin_audit import AdminActionLog
from app.models.base import User, UserRole
from app.models.catalog import Service, ServiceTranslation
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from app.models.store import Store
from tests._helpers import make_address

mock_admin = User(id=7501, email="pause-admin@kb.com", role=UserRole.Admin, is_active=True)
APPROVED_SELLER_UID = 7502
PENDING_SELLER_UID = 7503


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    session.add(User(**mock_admin.model_dump()))
    # Approved seller with store + service
    session.add(User(id=APPROVED_SELLER_UID, email="aps@kb.com", role=UserRole.Seller, is_active=True))
    # Pending seller, no store
    session.add(User(id=PENDING_SELLER_UID, email="pen@kb.com", role=UserRole.Seller, is_active=True))
    await session.flush()
    addr = Address(**make_address())
    session.add(addr)
    await session.flush()
    profile = SellerProfile(
        user_id=APPROVED_SELLER_UID, first_name="A", business_name="AP Store",
        phone="+919811117502", verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(profile)
    p_addr = Address(**make_address())
    session.add(p_addr)
    await session.flush()
    session.add(SellerProfile(
        user_id=PENDING_SELLER_UID, first_name="P", business_name="Pen Store",
        phone="+919811117503", verification_status=VerificationStatus.Pending,
        business_address_id=p_addr.id,
    ))
    svc = Service(slug="grocery-admin-pause")
    session.add(svc)
    await session.flush()
    session.add(ServiceTranslation(service_id=svc.id, language_code="en", name="Grocery"))
    session.add(SellerProfileService(seller_profile_id=profile.id, service_id=svc.id))
    store_addr = Address(**make_address())
    session.add(store_addr)
    await session.flush()
    store = Store(name="AP Store", seller_profile_id=profile.id, address_id=store_addr.id)
    session.add(store)
    await session.commit()
    yield {"service_id": svc.id, "store_id": store.id}


@pytest.fixture
def override_as_admin() -> Iterator[None]:
    app.dependency_overrides[get_current_admin] = lambda: mock_admin
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    yield None
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_pauses_store_and_audits(
    override_as_admin: Any, session: AsyncSession
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.patch(
            f"/api/v1/sellers/admin/{APPROVED_SELLER_UID}/store/pause",
            json={"is_paused": True, "reason": "Compliance hold"},
        )
        assert r.status_code == 200, r.text
    rows = (await session.exec(
        select(AdminActionLog).where(AdminActionLog.action == "store.set_pause")
    )).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_admin_pause_non_approved_seller_rejected(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.patch(
            f"/api/v1/sellers/admin/{PENDING_SELLER_UID}/store/pause",
            json={"is_paused": True},
        )
        assert r.status_code == 409
        assert r.json()["detail"] == "seller_not_active"
