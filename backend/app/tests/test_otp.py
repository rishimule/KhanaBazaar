"""OTP module unit tests — uses fakeredis, no Postgres required."""
import re
from collections.abc import AsyncGenerator

import fakeredis.aioredis
import pytest

from app.core.otp import (
    CodeExpired,
    InvalidCode,
    RateLimited,
    TooManyAttempts,
    consume_otp_key,
    generate_code,
    hash_code,
    request_otp,
    verify_otp,
)


@pytest.fixture(autouse=True)
async def setup_test_db() -> AsyncGenerator[None, None]:
    """No-op override — OTP tests need no database."""
    yield


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def test_generate_code_is_6_digits() -> None:
    for _ in range(20):
        code = generate_code()
        assert re.fullmatch(r"\d{6}", code), f"Got {code!r}"


def test_hash_code_is_sha256_hex_not_plaintext() -> None:
    code = "123456"
    hashed = hash_code(code)
    assert hashed != code
    assert re.fullmatch(r"[0-9a-f]{64}", hashed)


async def test_request_otp_stores_hashed_code(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    code = await request_otp("test@example.com", fake_redis)
    data = await fake_redis.hgetall("otp:code:test@example.com")
    assert data["code_hash"] == hash_code(code)
    assert data["code_hash"] != code
    assert int(data["attempts"]) == 0


async def test_request_otp_normalizes_email(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    await request_otp("  UPPER@Example.COM  ", fake_redis)
    assert await fake_redis.exists("otp:code:upper@example.com") == 1


async def test_verify_correct_code_returns_true(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    code = await request_otp("user@example.com", fake_redis)
    assert await verify_otp("user@example.com", code, fake_redis) is True


async def test_verify_wrong_code_raises_invalid_code(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    await request_otp("user@example.com", fake_redis)
    with pytest.raises(InvalidCode):
        await verify_otp("user@example.com", "000000", fake_redis)


async def test_verify_wrong_code_increments_attempts(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    await request_otp("user@example.com", fake_redis)
    with pytest.raises(InvalidCode):
        await verify_otp("user@example.com", "000000", fake_redis)
    data = await fake_redis.hgetall("otp:code:user@example.com")
    assert int(data["attempts"]) == 1


async def test_five_failures_raises_too_many_attempts(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    await request_otp("user@example.com", fake_redis)
    for _ in range(4):
        with pytest.raises(InvalidCode):
            await verify_otp("user@example.com", "000000", fake_redis)
    with pytest.raises(TooManyAttempts):
        await verify_otp("user@example.com", "000000", fake_redis)
    assert await fake_redis.exists("otp:code:user@example.com") == 0


async def test_missing_key_raises_code_expired(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    with pytest.raises(CodeExpired):
        await verify_otp("ghost@example.com", "123456", fake_redis)


async def test_resend_cooldown_blocks_second_request(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    await request_otp("user@example.com", fake_redis)
    with pytest.raises(RateLimited) as exc_info:
        await request_otp("user@example.com", fake_redis)
    assert exc_info.value.retry_after > 0


async def test_consume_deletes_all_keys(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    await request_otp("user@example.com", fake_redis)
    await consume_otp_key("user@example.com", fake_redis)
    assert await fake_redis.exists("otp:code:user@example.com") == 0
    assert await fake_redis.exists("otp:cooldown:user@example.com") == 0
    assert await fake_redis.exists("otp:hourly:user@example.com") == 0


async def test_verify_does_not_delete_key_on_success(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    code = await request_otp("user@example.com", fake_redis)
    await verify_otp("user@example.com", code, fake_redis)
    assert await fake_redis.exists("otp:code:user@example.com") == 1


async def test_hourly_cap_blocks_after_limit(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    from app.core.config import settings

    email = "cap@example.com"
    # Seed the hourly counter at the limit and remove any cooldown
    await fake_redis.set(f"otp:hourly:{email}", str(settings.OTP_MAX_PER_HOUR), ex=3600)

    with pytest.raises(RateLimited) as exc_info:
        await request_otp(email, fake_redis)
    assert exc_info.value.retry_after > 0
