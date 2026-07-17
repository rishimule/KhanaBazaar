# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import re
from datetime import timedelta
from typing import Any

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from app import app
from app.core.email import get_email_sender
from app.core.redis import get_redis
from app.models.auth_session import AuthSession


class _FakeSender:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, to: str, subject: str, *, text: str, html: Any = None,
                   reply_to: Any = None) -> None:
        self.sent.append({"to": to, "text": text})


def _code(text: str) -> str:
    m = re.search(r"\b(\d{6})\b", text)
    assert m
    return m.group(1)


@pytest.fixture
async def login_client() -> Any:
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    sender = _FakeSender()
    app.dependency_overrides[get_redis] = lambda: r
    app.dependency_overrides[get_email_sender] = lambda: sender
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield {"client": c, "sender": sender}
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_email_sender, None)


async def test_verify_new_user_remember_creates_trusted_session(
    login_client: dict[str, Any], session: Any
) -> None:
    c = login_client["client"]
    sender = login_client["sender"]
    await c.post("/api/v1/auth/otp/request", json={"email": "trust@example.com"})
    code = _code(sender.sent[-1]["text"])
    resp = await c.post(
        "/api/v1/auth/otp/verify",
        json={
            "email": "trust@example.com",
            "code": code,
            "full_name": "Trust Me",
            "remember": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["refresh_token"]
    assert data["expires_in"] == 15 * 60

    row = (await session.exec(select(AuthSession))).one()
    assert row.trusted is True
    delta = row.absolute_expires_at - row.created_at
    assert delta > timedelta(days=179)

    # The returned refresh token works against /auth/refresh.
    ref = await c.post(
        "/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]}
    )
    assert ref.status_code == 200


async def test_verify_without_remember_is_untrusted_24h(
    login_client: dict[str, Any], session: Any
) -> None:
    c = login_client["client"]
    sender = login_client["sender"]
    await c.post("/api/v1/auth/otp/request", json={"email": "guest@example.com"})
    code = _code(sender.sent[-1]["text"])
    resp = await c.post(
        "/api/v1/auth/otp/verify",
        json={"email": "guest@example.com", "code": code, "full_name": "Guest U"},
    )
    assert resp.status_code == 200
    row = (await session.exec(select(AuthSession))).one()
    assert row.trusted is False
    delta = row.absolute_expires_at - row.created_at
    assert delta < timedelta(hours=25)
