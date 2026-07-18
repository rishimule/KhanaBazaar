# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import re
from typing import Any
from unittest.mock import patch

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from app.core.email import get_email_sender
from app.core.redis import get_redis


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
async def alert_client() -> Any:
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    sender = _FakeSender()
    app.dependency_overrides[get_redis] = lambda: r
    app.dependency_overrides[get_email_sender] = lambda: sender
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield {"client": c, "sender": sender}
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_email_sender, None)


async def test_trusted_login_dispatches_new_device_email(
    alert_client: dict[str, Any], session: Any
) -> None:
    c, sender = alert_client["client"], alert_client["sender"]
    with patch("app.api.auth.dispatch_new_device_login") as m:
        await c.post("/api/v1/auth/otp/request", json={"email": "nd@example.com"})
        code = _code(sender.sent[-1]["text"])
        resp = await c.post(
            "/api/v1/auth/otp/verify",
            json={"email": "nd@example.com", "code": code,
                  "full_name": "N D", "remember": True},
        )
        assert resp.status_code == 200
        assert m.called


async def test_untrusted_login_does_not_dispatch(
    alert_client: dict[str, Any], session: Any
) -> None:
    c, sender = alert_client["client"], alert_client["sender"]
    with patch("app.api.auth.dispatch_new_device_login") as m:
        await c.post("/api/v1/auth/otp/request", json={"email": "nd2@example.com"})
        code = _code(sender.sent[-1]["text"])
        resp = await c.post(
            "/api/v1/auth/otp/verify",
            json={"email": "nd2@example.com", "code": code, "full_name": "N D2"},
        )
        assert resp.status_code == 200
        assert not m.called
