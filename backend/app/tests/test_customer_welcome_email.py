# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Customer welcome email is dispatched only on first OTP-verify."""

from typing import Any
from unittest.mock import patch

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from app.core.email import get_email_sender
from app.core.otp import hash_code
from app.core.redis import get_redis


class _NoopSender:
    async def send(self, *args: Any, **kwargs: Any) -> None:
        pass


def _seed_otp_code(redis: fakeredis.aioredis.FakeRedis, email: str, code: str) -> None:
    """Plant a valid OTP record in Redis so /verify succeeds without /request."""
    import asyncio

    async def _seed() -> None:
        await redis.hset(
            f"otp:email:code:{email}",
            mapping={"code_hash": hash_code(code), "attempts": "0"},
        )
        await redis.expire(f"otp:email:code:{email}", 600)

    asyncio.get_event_loop().run_until_complete(_seed())


@pytest.fixture
async def auth_env():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_email_sender] = lambda: _NoopSender()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield {"client": client, "redis": redis}
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_email_sender, None)


async def test_first_otp_verify_enqueues_welcome(auth_env):
    enqueued: list[tuple] = []
    from app.worker import send_customer_welcome_async

    redis = auth_env["redis"]
    code = "123456"
    await redis.hset(
        "otp:email:code:newuser@example.com",
        mapping={"code_hash": hash_code(code), "attempts": "0"},
    )
    await redis.expire("otp:email:code:newuser@example.com", 600)

    with patch.object(
        send_customer_welcome_async, "delay", lambda *a, **k: enqueued.append(a)
    ):
        resp = await auth_env["client"].post(
            "/api/v1/auth/otp/verify",
            json={"email": "newuser@example.com", "code": code, "full_name": "Ravi Kumar"},
        )

    assert resp.status_code == 200, resp.text
    assert len(enqueued) == 1


async def test_returning_user_otp_verify_does_not_enqueue_welcome(auth_env):
    enqueued: list[tuple] = []
    from app.worker import send_customer_welcome_async

    redis = auth_env["redis"]
    email = "returning@example.com"
    code = "654321"

    # First verify — creates user. Drain that enqueue.
    await redis.hset(
        f"otp:email:code:{email}",
        mapping={"code_hash": hash_code(code), "attempts": "0"},
    )
    await redis.expire(f"otp:email:code:{email}", 600)
    with patch.object(send_customer_welcome_async, "delay", lambda *a, **k: None):
        resp1 = await auth_env["client"].post(
            "/api/v1/auth/otp/verify",
            json={"email": email, "code": code, "full_name": "Existing User"},
        )
    assert resp1.status_code == 200, resp1.text

    # Second verify — should NOT re-enqueue.
    await redis.hset(
        f"otp:email:code:{email}",
        mapping={"code_hash": hash_code(code), "attempts": "0"},
    )
    await redis.expire(f"otp:email:code:{email}", 600)
    with patch.object(
        send_customer_welcome_async, "delay", lambda *a, **k: enqueued.append(a)
    ):
        resp2 = await auth_env["client"].post(
            "/api/v1/auth/otp/verify",
            json={"email": email, "code": code},
        )
    assert resp2.status_code == 200, resp2.text
    assert enqueued == []
