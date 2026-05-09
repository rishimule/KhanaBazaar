# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import re
from collections.abc import AsyncGenerator
from typing import Any

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from app.core.email import get_email_sender
from app.core.redis import get_redis


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, to: str, subject: str, text: str) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text})


def _extract_code(text: str) -> str:
    match = re.search(r"\b(\d{6})\b", text)
    assert match, f"No 6-digit code found in: {text!r}"
    return match.group(1)


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def fake_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
async def auth_client(
    fake_redis: fakeredis.aioredis.FakeRedis,
    fake_sender: FakeEmailSender,
) -> AsyncGenerator[dict[str, Any], None]:
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_email_sender] = lambda: fake_sender
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"client": client, "redis": fake_redis, "sender": fake_sender}
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_email_sender, None)


async def test_otp_request_returns_ok(auth_client: dict[str, Any]) -> None:
    resp = await auth_client["client"].post(
        "/api/v1/auth/otp/request", json={"email": "user@example.com"}
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert len(auth_client["sender"].sent) == 1


async def test_otp_request_same_response_for_unknown_email(auth_client: dict[str, Any]) -> None:
    resp = await auth_client["client"].post(
        "/api/v1/auth/otp/request", json={"email": "brand-new@example.com"}
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


async def test_returning_user_gets_token(auth_client: dict[str, Any], session: Any) -> None:
    from app.models.base import User, UserRole
    from app.models.profile import CustomerProfile

    user = User(email="returning@example.com", role=UserRole.Customer)
    session.add(user)
    await session.flush()
    session.add(CustomerProfile(user_id=user.id, first_name="Ret", last_name=None))
    await session.commit()

    c = auth_client["client"]
    sender = auth_client["sender"]
    await c.post("/api/v1/auth/otp/request", json={"email": "returning@example.com"})
    code = _extract_code(sender.sent[-1]["text"])
    resp = await c.post(
        "/api/v1/auth/otp/verify",
        json={"email": "returning@example.com", "code": code},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_name"] is False
    assert data["access_token"] is not None
    assert data["user"]["email"] == "returning@example.com"


async def test_new_user_needs_name_then_gets_token(
    auth_client: dict[str, Any], session: Any
) -> None:
    c = auth_client["client"]
    sender = auth_client["sender"]

    await c.post("/api/v1/auth/otp/request", json={"email": "new@example.com"})
    code = _extract_code(sender.sent[-1]["text"])

    resp1 = await c.post(
        "/api/v1/auth/otp/verify", json={"email": "new@example.com", "code": code}
    )
    assert resp1.status_code == 200
    assert resp1.json()["needs_name"] is True
    assert resp1.json()["access_token"] is None

    resp2 = await c.post(
        "/api/v1/auth/otp/verify",
        json={"email": "new@example.com", "code": code, "full_name": "New User"},
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["needs_name"] is False
    assert data["access_token"] is not None
    assert data["user"]["full_name"] == "New User"
    assert data["user"]["role"] == "customer"

    from sqlmodel import select

    from app.models.profile import CustomerProfile

    result = await session.exec(select(CustomerProfile))
    profile = result.one()
    assert profile.first_name == "New"
    assert profile.last_name == "User"


async def test_wrong_code_returns_400(auth_client: dict[str, Any]) -> None:
    await auth_client["client"].post(
        "/api/v1/auth/otp/request", json={"email": "user@example.com"}
    )
    resp = await auth_client["client"].post(
        "/api/v1/auth/otp/verify",
        json={"email": "user@example.com", "code": "000000"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_code"


async def test_five_wrong_codes_returns_429(auth_client: dict[str, Any]) -> None:
    c = auth_client["client"]
    await c.post("/api/v1/auth/otp/request", json={"email": "user@example.com"})
    for _ in range(4):
        await c.post(
            "/api/v1/auth/otp/verify",
            json={"email": "user@example.com", "code": "000000"},
        )
    resp = await c.post(
        "/api/v1/auth/otp/verify",
        json={"email": "user@example.com", "code": "000000"},
    )
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"] == "too_many_attempts"


async def test_missing_key_returns_410(auth_client: dict[str, Any]) -> None:
    resp = await auth_client["client"].post(
        "/api/v1/auth/otp/verify",
        json={"email": "ghost@example.com", "code": "123456"},
    )
    assert resp.status_code == 410
    assert resp.json()["detail"]["error"] == "code_expired_or_used"


async def test_rapid_resend_returns_429(auth_client: dict[str, Any]) -> None:
    c = auth_client["client"]
    await c.post("/api/v1/auth/otp/request", json={"email": "user@example.com"})
    resp = await c.post("/api/v1/auth/otp/request", json={"email": "user@example.com"})
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"] == "rate_limited"


async def test_me_endpoint_returns_authenticated_user(auth_client: dict[str, Any]) -> None:
    c = auth_client["client"]
    sender = auth_client["sender"]
    await c.post("/api/v1/auth/otp/request", json={"email": "me@example.com"})
    code = _extract_code(sender.sent[-1]["text"])
    verify = await c.post(
        "/api/v1/auth/otp/verify",
        json={"email": "me@example.com", "code": code, "full_name": "Test Me"},
    )
    token = verify.json()["access_token"]
    resp = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"
