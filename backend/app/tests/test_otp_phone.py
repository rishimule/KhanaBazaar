# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Tests for the namespaced OTP helpers and phone normalization."""
from collections.abc import AsyncGenerator

import pytest
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.otp import (
    InvalidPhoneNumber,
    consume_otp_key,
    hash_code,
    normalize_phone,
    request_otp,
    verify_otp,
)


def test_normalize_phone_accepts_indian_e164() -> None:
    assert normalize_phone("+919876543210") == "+919876543210"
    assert normalize_phone(" +91 98765 43210 ") == "+919876543210"
    assert normalize_phone("+91-9876543210") == "+919876543210"


def test_normalize_phone_rejects_other_formats() -> None:
    bad_inputs = (
        "9876543210",        # missing +91
        "+1234567890",       # wrong country
        "+91 1234567890",    # starts with 1, not [6-9]
        "+91987654321",      # 9 digits
        "+9198765432101",    # 11 digits
        "",
    )
    for bad in bad_inputs:
        with pytest.raises(InvalidPhoneNumber):
            normalize_phone(bad)


@pytest.fixture
async def redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    client: aioredis.Redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    async for key in client.scan_iter("otp:phone:*"):
        await client.delete(key)
    async for key in client.scan_iter("otp:email:*"):
        await client.delete(key)
    yield client
    async for key in client.scan_iter("otp:phone:*"):
        await client.delete(key)
    async for key in client.scan_iter("otp:email:*"):
        await client.delete(key)
    await client.aclose()


async def test_namespaced_request_uses_phone_prefix(redis_client: aioredis.Redis) -> None:
    phone = "+919876543210"
    code = await request_otp(phone, redis_client, namespace="phone")
    stored = await redis_client.hget(f"otp:phone:code:{phone}", "code_hash")  # type: ignore[misc]
    assert stored == hash_code(code)


async def test_namespaced_verify_and_consume(redis_client: aioredis.Redis) -> None:
    phone = "+919876543210"
    code = await request_otp(phone, redis_client, namespace="phone")
    assert await verify_otp(phone, code, redis_client, namespace="phone") is True
    await consume_otp_key(phone, redis_client, namespace="phone")
    assert await redis_client.exists(f"otp:phone:code:{phone}") == 0


async def test_email_default_namespace_uses_email_prefix(redis_client: aioredis.Redis) -> None:
    """request_otp() called with no namespace argument writes to the
    `otp:email:code:{email}` key shape."""
    email = "user@example.com"
    code = await request_otp(email, redis_client)
    stored = await redis_client.hget(f"otp:email:code:{email}", "code_hash")  # type: ignore[misc]
    assert stored == hash_code(code)
    await consume_otp_key(email, redis_client)
