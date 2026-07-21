# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.redis import get_redis
from app.core.security import get_current_customer, get_current_user
from app.db.session import async_session_factory
from app.models.base import AccountStatus, User, UserRole
from app.models.profile import CustomerProfile


async def _seed_and_login(session: AsyncSession, email: str) -> User:
    user = User(email=email, role=UserRole.Customer)
    session.add(user)
    await session.flush()
    assert user.id is not None
    session.add(CustomerProfile(user_id=user.id, first_name="Self"))
    await session.commit()
    await session.refresh(user)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_customer] = lambda: user
    return user


def _clear_overrides() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_customer, None)


async def _status(user_id: int) -> AccountStatus:
    async with async_session_factory() as s2:
        u = (await s2.exec(select(User).where(User.id == user_id))).first()
        assert u is not None
        return u.account_status


@pytest.mark.asyncio
async def test_deactivate_sets_status(session: AsyncSession) -> None:
    user = await _seed_and_login(session, "self-deac@kb.com")
    assert user.id is not None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/customers/me/deactivate", json={})
        assert resp.status_code == 200, resp.text
        assert await _status(user.id) == AccountStatus.deactivated
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_delete_otp_request_returns_ok(session: AsyncSession) -> None:
    await _seed_and_login(session, "self-delreq@kb.com")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            req = await ac.post("/api/v1/customers/me/delete/otp/request", json={})
        assert req.status_code == 200, req.text
        assert req.json() == {"sent": True}
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_delete_rejects_wrong_code_then_deletes(session: AsyncSession) -> None:
    user = await _seed_and_login(session, "self-del@kb.com")
    assert user.id is not None
    try:
        # The delete handler calls get_redis() directly (not via Depends), so it
        # uses the REAL redis — seed the confirmation code there once.
        redis = await get_redis()
        from app.core.otp import request_otp

        code = await request_otp("self-del@kb.com", redis, namespace="account_delete")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            bad = await ac.post("/api/v1/customers/me/delete", json={"code": "000000"})
            assert bad.status_code == 422
            assert await _status(user.id) == AccountStatus.active  # unchanged
            ok = await ac.post("/api/v1/customers/me/delete", json={"code": code})
        assert ok.status_code == 200, ok.text
        assert await _status(user.id) == AccountStatus.deleted
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_me_exposes_account_status(session: AsyncSession) -> None:
    await _seed_and_login(session, "self-status@kb.com")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/customers/me")
        assert resp.status_code == 200, resp.text
        assert resp.json()["account_status"] == "active"
    finally:
        _clear_overrides()
