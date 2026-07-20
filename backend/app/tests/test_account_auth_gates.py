# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.redis import get_redis
from app.core.security import get_current_user
from app.models.base import AccountStatus, User, UserRole
from app.models.profile import CustomerProfile


async def _seed(session: AsyncSession, email: str, status: AccountStatus) -> User:
    user = User(
        email=email, role=UserRole.Customer, account_status=status,
        is_active=status == AccountStatus.active,
    )
    session.add(user)
    await session.flush()
    assert user.id is not None
    session.add(CustomerProfile(user_id=user.id, first_name="Gate"))
    await session.commit()
    await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_get_current_user_rejects_suspended(session: AsyncSession) -> None:
    user = await _seed(session, "gate-susp@kb.com", AccountStatus.suspended)
    with pytest.raises(HTTPException) as exc:
        await get_current_user(payload={"sub": str(user.id)}, session=session)
    assert exc.value.status_code == 403
    assert exc.value.detail == {"error": "account_suspended"}


@pytest.mark.asyncio
async def test_login_blocks_deleted(session: AsyncSession) -> None:
    await _seed(session, "gate-del@kb.com", AccountStatus.deleted)
    redis = await app.dependency_overrides[get_redis]()
    from app.core.otp import request_otp

    code = await request_otp("gate-del@kb.com", redis)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/otp/verify", json={"email": "gate-del@kb.com", "code": code}
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "account_deleted"


@pytest.mark.asyncio
async def test_login_blocks_suspended(session: AsyncSession) -> None:
    await _seed(session, "gate-susp-login@kb.com", AccountStatus.suspended)
    redis = await app.dependency_overrides[get_redis]()
    from app.core.otp import request_otp

    code = await request_otp("gate-susp-login@kb.com", redis)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/otp/verify",
            json={"email": "gate-susp-login@kb.com", "code": code},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "account_suspended"


@pytest.mark.asyncio
async def test_login_reactivates_deactivated(session: AsyncSession) -> None:
    user = await _seed(session, "gate-deac@kb.com", AccountStatus.deactivated)
    redis = await app.dependency_overrides[get_redis]()
    from app.core.otp import request_otp

    code = await request_otp("gate-deac@kb.com", redis)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/otp/verify", json={"email": "gate-deac@kb.com", "code": code}
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    # The endpoint committed in its own request session; read through a fresh
    # session (the fixture session holds a stale snapshot).
    from app.db.session import async_session_factory

    async with async_session_factory() as s2:
        refreshed = (await s2.exec(select(User).where(User.id == user.id))).first()
    assert refreshed is not None and refreshed.account_status == AccountStatus.active
