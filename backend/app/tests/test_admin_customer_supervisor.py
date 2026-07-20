# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_user
from app.db.session import async_session_factory
from app.models.base import AccountStatus, User, UserRole
from app.models.profile import CustomerProfile


async def _seed_customer(session: AsyncSession, email: str) -> CustomerProfile:
    user = User(email=email, role=UserRole.Customer)
    session.add(user)
    await session.flush()
    assert user.id is not None
    profile = CustomerProfile(user_id=user.id, first_name="Cust")
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def _status_of(user_id: int) -> AccountStatus:
    async with async_session_factory() as s2:
        u = (await s2.exec(select(User).where(User.id == user_id))).first()
        assert u is not None
        return u.account_status


@pytest.fixture(name="as_admin")
def as_admin_fixture(session: AsyncSession) -> Generator[User, None, None]:
    admin = User(id=99001, email="admin-cust@kb.com", role=UserRole.Admin, is_active=True)
    app.dependency_overrides[get_current_admin] = lambda: admin
    app.dependency_overrides[get_current_user] = lambda: admin
    yield admin
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


async def _persist_admin() -> None:
    # The audit/status FKs (actor_user_id) reference user.id, so the admin the
    # override injects must also exist as a real row.
    async with async_session_factory() as s2:
        existing = (await s2.exec(select(User).where(User.id == 99001))).first()
        if existing is None:
            s2.add(User(id=99001, email="admin-cust@kb.com", role=UserRole.Admin))
            await s2.commit()


@pytest.mark.asyncio
async def test_admin_suspend_and_unsuspend(
    session: AsyncSession, as_admin: User
) -> None:
    await _persist_admin()
    profile = await _seed_customer(session, "cust-susp@kb.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r1 = await ac.post(
            f"/api/v1/admin/customers/{profile.id}/suspend",
            json={"reason": "policy violation review"},
        )
        assert r1.status_code == 200, r1.text
        assert await _status_of(profile.user_id) == AccountStatus.suspended

        r2 = await ac.post(
            f"/api/v1/admin/customers/{profile.id}/unsuspend",
            json={"reason": "cleared after review"},
        )
        assert r2.status_code == 200, r2.text
        assert await _status_of(profile.user_id) == AccountStatus.active


@pytest.mark.asyncio
async def test_admin_cannot_target_non_customer(
    session: AsyncSession, as_admin: User
) -> None:
    await _persist_admin()
    # A customer_profile_id that does not exist -> 404.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/admin/customers/999999/suspend",
            json={"reason": "should not resolve"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_delete_and_restore(
    session: AsyncSession, as_admin: User
) -> None:
    await _persist_admin()
    profile = await _seed_customer(session, "cust-delrestore@kb.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        d = await ac.post(
            f"/api/v1/admin/customers/{profile.id}/delete",
            json={"reason": "spam account removal"},
        )
        assert d.status_code == 200, d.text
        assert await _status_of(profile.user_id) == AccountStatus.deleted
        r = await ac.post(
            f"/api/v1/admin/customers/{profile.id}/restore",
            json={"reason": "appeal granted here"},
        )
        assert r.status_code == 200, r.text
        assert await _status_of(profile.user_id) == AccountStatus.active


@pytest.mark.asyncio
async def test_short_reason_rejected(session: AsyncSession, as_admin: User) -> None:
    await _persist_admin()
    profile = await _seed_customer(session, "cust-shortreason@kb.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/v1/admin/customers/{profile.id}/suspend", json={"reason": "short"}
        )
    assert resp.status_code == 422  # reason min_length=10


@pytest.mark.asyncio
async def test_admin_list_hub_and_activity(
    session: AsyncSession, as_admin: User
) -> None:
    await _persist_admin()
    profile = await _seed_customer(session, "cust-hub@kb.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        lst = await ac.get("/api/v1/admin/customers?q=cust-hub")
        assert lst.status_code == 200, lst.text
        assert any(item["email"] == "cust-hub@kb.com" for item in lst.json()["items"])

        hub = await ac.get(f"/api/v1/admin/customers/{profile.id}")
        assert hub.status_code == 200, hub.text
        assert hub.json()["account_status"] == "active"
        assert hub.json()["open_orders"] == 0

        # Create one event via a suspend, then read the activity feed.
        await ac.post(
            f"/api/v1/admin/customers/{profile.id}/suspend",
            json={"reason": "activity feed check"},
        )
        act = await ac.get(f"/api/v1/admin/customers/{profile.id}/activity")
        assert act.status_code == 200
        assert any(e["to_status"] == "suspended" for e in act.json())


@pytest.mark.asyncio
async def test_admin_customer_read_viewers(
    session: AsyncSession, as_admin: User
) -> None:
    await _persist_admin()
    profile = await _seed_customer(session, "cust-viewers@kb.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        orders = await ac.get(f"/api/v1/admin/customers/{profile.id}/orders")
        addrs = await ac.get(f"/api/v1/admin/customers/{profile.id}/addresses")
        notifs = await ac.get(f"/api/v1/admin/customers/{profile.id}/notifications")
    assert orders.status_code == 200 and orders.json() == []
    assert addrs.status_code == 200 and addrs.json() == []
    assert notifs.status_code == 200 and notifs.json() == []
