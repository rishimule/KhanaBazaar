# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token, get_optional_current_user
from app.db.session import get_db_session
from app.models.base import User, UserRole


def _make_probe_app(session_override):
    probe = FastAPI()
    probe.dependency_overrides[get_db_session] = session_override

    @probe.get("/whoami")
    async def whoami(user=Depends(get_optional_current_user)):
        return {"user_id": user.id if user else None}

    return probe


@pytest.mark.asyncio
async def test_optional_auth_returns_none_without_token(session):
    async def _sess():
        yield session

    app_ = _make_probe_app(_sess)
    async with AsyncClient(
        transport=ASGITransport(app=app_), base_url="http://t"
    ) as ac:
        r = await ac.get("/whoami")
    assert r.status_code == 200
    assert r.json() == {"user_id": None}


@pytest.mark.asyncio
async def test_optional_auth_returns_none_for_garbage_token(session):
    async def _sess():
        yield session

    app_ = _make_probe_app(_sess)
    async with AsyncClient(
        transport=ASGITransport(app=app_), base_url="http://t"
    ) as ac:
        r = await ac.get("/whoami", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 200
    assert r.json() == {"user_id": None}


@pytest.mark.asyncio
async def test_optional_auth_resolves_valid_token(session):
    user = User(email="opt@example.com", role=UserRole.Customer, is_active=True)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    token = create_access_token(user)

    async def _sess():
        yield session

    app_ = _make_probe_app(_sess)
    async with AsyncClient(
        transport=ASGITransport(app=app_), base_url="http://t"
    ) as ac:
        r = await ac.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"user_id": user.id}
