# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Backend coverage for the admin force-logout-a-seller's-sessions endpoint."""
from typing import AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import SellerProfile
from app.services.sessions import create_session
from tests._helpers import make_address

mock_admin = User(id=901, email="adm-revoke@kb.com", role=UserRole.Admin, is_active=True)


@pytest.fixture
def override_as_admin() -> Iterator[None]:
    app.dependency_overrides[get_current_admin] = lambda: mock_admin
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    yield None
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def seller_with_sessions(session: AsyncSession) -> AsyncGenerator[User, None]:
    session.add(User(**mock_admin.model_dump()))
    user = User(email="revoke-seller@x.test", role=UserRole.Seller)
    session.add(user)
    await session.flush()
    addr = Address(**make_address())
    session.add(addr)
    await session.flush()
    session.add(
        SellerProfile(
            user_id=user.id,
            first_name="S",
            last_name="P",
            business_name="Biz",
            phone="+919000000001",
            business_address_id=addr.id,
        )
    )
    await session.flush()
    await create_session(session, user=user, trusted=True)
    await create_session(session, user=user, trusted=True)
    await session.commit()
    await session.refresh(user)
    yield user


@pytest.mark.asyncio
async def test_admin_revoke_seller_sessions(
    seller_with_sessions: User, override_as_admin: None, session: AsyncSession
) -> None:
    from app.models.admin_audit import AdminActionLog

    seller = seller_with_sessions
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/admin/sellers/{seller.id}/revoke-sessions")
    assert resp.status_code == 200, resp.text
    assert resp.json()["revoked"] == 2

    log = (await session.exec(select(AdminActionLog))).all()
    assert any(r.action == "user.revoke_sessions" for r in log)


@pytest.mark.asyncio
async def test_admin_revoke_unknown_seller_404(override_as_admin: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/admin/sellers/99999/revoke-sessions")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "seller_not_found"
