import hashlib
import hmac
import secrets

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.rate_limit import incr_with_ttl, seconds_until


def normalize_email(email: str) -> str:
    return email.strip().lower()


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(f"{settings.OTP_PEPPER}{code}".encode()).hexdigest()


def _key_code(email: str) -> str:
    return f"otp:code:{email}"


def _key_cooldown(email: str) -> str:
    return f"otp:cooldown:{email}"


def _key_hourly(email: str) -> str:
    return f"otp:hourly:{email}"


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


class InvalidCode(Exception):
    pass


class CodeExpired(Exception):
    pass


class TooManyAttempts(Exception):
    pass


async def request_otp(email: str, redis: aioredis.Redis) -> str:
    """Store a new OTP in Redis. Returns the plaintext code for the caller to send."""
    email = normalize_email(email)

    cooldown = await seconds_until(redis, _key_cooldown(email))
    if cooldown > 0:
        raise RateLimited(retry_after=cooldown)

    hourly = await incr_with_ttl(redis, _key_hourly(email), 3600)
    if hourly > settings.OTP_MAX_PER_HOUR:
        raise RateLimited(retry_after=await seconds_until(redis, _key_hourly(email)))

    code = generate_code()
    pipe = redis.pipeline()
    pipe.hset(_key_code(email), mapping={"code_hash": hash_code(code), "attempts": "0"})
    pipe.expire(_key_code(email), settings.OTP_TTL_SECONDS)
    pipe.set(_key_cooldown(email), "1", ex=settings.OTP_RESEND_COOLDOWN)
    await pipe.execute()

    return code


async def verify_otp(email: str, code: str, redis: aioredis.Redis) -> bool:
    """Verify OTP code. Returns True on match; does NOT delete the key.

    Raises CodeExpired, InvalidCode, or TooManyAttempts on failure.
    Caller must call consume_otp_key() after successful auth.
    """
    email = normalize_email(email)
    data: dict[str, str] = await redis.hgetall(_key_code(email))  # type: ignore[misc]
    if not data:
        raise CodeExpired()

    if hmac.compare_digest(data.get("code_hash", ""), hash_code(code)):
        return True

    attempts = await redis.hincrby(_key_code(email), "attempts", 1)  # type: ignore[misc]
    if int(attempts) >= settings.OTP_MAX_ATTEMPTS:
        await redis.delete(_key_code(email))
        raise TooManyAttempts()
    raise InvalidCode()


async def consume_otp_key(email: str, redis: aioredis.Redis) -> None:
    """Delete OTP code key and rate-limit counters after successful auth."""
    email = normalize_email(email)
    await redis.delete(_key_code(email), _key_cooldown(email), _key_hourly(email))
