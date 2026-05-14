# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import re
from typing import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core import redis as redis_module
from app.core.security import get_current_customer
from app.core.sms import SMSSender, get_sms_sender
from app.models.base import User, UserRole
from app.models.profile import CustomerProfile

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _reset_redis_cache() -> AsyncGenerator[None, None]:
    """Drop the lru_cached aioredis client so each test gets a fresh connection
    bound to the current event loop."""
    redis_module._make_redis.cache_clear()
    yield
    redis_module._make_redis.cache_clear()


class _CapturingSMS(SMSSender):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, to: str, text: str) -> None:
        self.sent.append((to, text))


def _extract_code(text: str) -> str:
    match = re.search(r"\b(\d{6})\b", text)
    assert match, f"no 6-digit code in: {text}"
    return match.group(1)


class _Ids:
    def __init__(self, **kwargs: int | str) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


async def _make_customer(
    session: AsyncSession, email: str = "phone@example.com"
) -> _Ids:
    user = User(email=email, role=UserRole.Customer, is_active=True)
    session.add(user)
    await session.flush()
    assert user.id is not None
    profile = CustomerProfile(user_id=user.id, first_name="X")
    session.add(profile)
    await session.flush()
    assert profile.id is not None
    return _Ids(user_id=user.id, profile_id=profile.id, email=email)


def _user_for(ids: _Ids) -> User:
    return User(
        id=ids.user_id,  # type: ignore[attr-defined]
        email=ids.email,  # type: ignore[attr-defined]
        role=UserRole.Customer,
        is_active=True,
    )


async def test_phone_otp_happy_path(client: AsyncClient, session: AsyncSession):
    ids = await _make_customer(session)
    await session.commit()
    fake_sms = _CapturingSMS()
    app.dependency_overrides[get_current_customer] = lambda: _user_for(ids)
    app.dependency_overrides[get_sms_sender] = lambda: fake_sms
    try:
        r = await client.post(
            "/api/v1/customers/me/phone/otp/request",
            json={"phone": "+919876543210"},
        )
        assert r.status_code == 200, r.text
        assert len(fake_sms.sent) == 1
        assert fake_sms.sent[0][0] == "+919876543210"
        code = _extract_code(fake_sms.sent[0][1])
        r2 = await client.post(
            "/api/v1/customers/me/phone/otp/verify",
            json={"phone": "+919876543210", "code": code},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
        app.dependency_overrides.pop(get_sms_sender, None)
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["phone"] == "+919876543210"
    assert data["phone_verified_at"] is not None


async def test_phone_otp_wrong_code(client: AsyncClient, session: AsyncSession):
    ids = await _make_customer(session, email="phone2@example.com")
    await session.commit()
    fake_sms = _CapturingSMS()
    app.dependency_overrides[get_current_customer] = lambda: _user_for(ids)
    app.dependency_overrides[get_sms_sender] = lambda: fake_sms
    try:
        await client.post(
            "/api/v1/customers/me/phone/otp/request",
            json={"phone": "+919876543211"},
        )
        r = await client.post(
            "/api/v1/customers/me/phone/otp/verify",
            json={"phone": "+919876543211", "code": "000000"},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
        app.dependency_overrides.pop(get_sms_sender, None)
    assert r.status_code == 422, r.text


async def test_phone_otp_invalid_phone(client: AsyncClient, session: AsyncSession):
    ids = await _make_customer(session, email="phone3@example.com")
    await session.commit()
    app.dependency_overrides[get_current_customer] = lambda: _user_for(ids)
    try:
        r = await client.post(
            "/api/v1/customers/me/phone/otp/request",
            json={"phone": "1234567890"},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 422


async def test_phone_already_in_use(client: AsyncClient, session: AsyncSession):
    # Seed another customer with phone set.
    other = await _make_customer(session, email="other@example.com")
    other_profile = (
        await session.exec(
            __import__("sqlmodel").select(CustomerProfile).where(
                CustomerProfile.id == other.profile_id  # type: ignore[attr-defined]
            )
        )
    ).first()
    assert other_profile is not None
    other_profile.phone = "+919999999999"
    session.add(other_profile)
    await session.commit()

    ids = await _make_customer(session, email="me@example.com")
    await session.commit()
    app.dependency_overrides[get_current_customer] = lambda: _user_for(ids)
    try:
        r = await client.post(
            "/api/v1/customers/me/phone/otp/request",
            json={"phone": "+919999999999"},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "phone_already_in_use"
