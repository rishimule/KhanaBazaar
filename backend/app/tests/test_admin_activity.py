# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Backend coverage for the admin activity log endpoint."""
from datetime import datetime, timezone
from typing import AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_user
from app.models.address import Address
from app.models.admin_audit import AdminActionLog, AdminActionTargetType
from app.models.base import User, UserRole
from app.models.profile import SellerProfile, VerificationStatus
from app.services.admin_audit import log as audit_log
from tests._helpers import make_address

mock_admin = User(id=801, email="adm-act@kb.com", role=UserRole.Admin, is_active=True)
mock_customer = User(id=802, email="cust-act@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=803, email="sel-act@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture(autouse=True)
async def seed_activity(session: AsyncSession) -> AsyncGenerator[dict, None]:
    for u in (mock_admin, mock_customer, mock_seller):
        session.add(User(**u.model_dump()))
    await session.flush()
    addr = Address(**make_address())
    session.add(addr)
    await session.flush()
    profile = SellerProfile(
        user_id=mock_seller.id,
        first_name="Act",
        business_name="Activity Test Store",
        phone="+919800000801",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(profile)
    await session.flush()
    seller_profile_id = profile.id
    seller_user_id = mock_seller.id  # what the FE/URL uses
    admin_id = mock_admin.id
    await session.commit()

    # Insert three audit rows with monotonically increasing created_at.
    for i, action in enumerate(["inventory.create", "inventory.update", "order.cancel"]):
        await audit_log(
            session=session,
            admin_user_id=admin_id,
            target_seller_id=seller_profile_id,
            target_type=(
                AdminActionTargetType.Order
                if action.startswith("order")
                else AdminActionTargetType.Inventory
            ),
            target_id=100 + i,
            action=action,
            before_json={"x": i},
            after_json={"x": i + 1},
        )
        await session.commit()

    yield {
        "seller_user_id": seller_user_id,
        "seller_profile_id": seller_profile_id,
        "admin_id": admin_id,
    }


@pytest.fixture
def override_as_admin() -> Iterator[None]:
    app.dependency_overrides[get_current_admin] = lambda: mock_admin
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    yield None
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_as_customer() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    yield None
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_activity_returns_newest_first(
    seed_activity: dict, override_as_admin: None
) -> None:
    s = seed_activity
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/admin/sellers/{s['seller_user_id']}/activity")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["items"]
    assert len(items) == 3
    # Newest first ordering — last action emitted was order.cancel.
    assert items[0]["action"] == "order.cancel"
    assert items[1]["action"] == "inventory.update"
    assert items[2]["action"] == "inventory.create"
    # admin email is joined
    assert items[0]["admin_email"] == "adm-act@kb.com"


@pytest.mark.asyncio
async def test_activity_cursor_paginates(
    seed_activity: dict, override_as_admin: None
) -> None:
    s = seed_activity
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r1 = await ac.get(
            f"/api/v1/admin/sellers/{s['seller_user_id']}/activity",
            params={"limit": 2},
        )
        body = r1.json()
        assert len(body["items"]) == 2
        cursor = body["next_cursor"]
        assert cursor is not None

        r2 = await ac.get(
            f"/api/v1/admin/sellers/{s['seller_user_id']}/activity",
            params={"limit": 2, "cursor": cursor},
        )
    page2 = r2.json()
    assert len(page2["items"]) == 1
    assert page2["items"][0]["id"] != body["items"][-1]["id"]
    assert page2["next_cursor"] is None  # no more rows


@pytest.mark.asyncio
async def test_activity_non_admin_forbidden(
    seed_activity: dict, override_as_customer: None
) -> None:
    s = seed_activity
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/admin/sellers/{s['seller_user_id']}/activity")
    assert resp.status_code == 403
