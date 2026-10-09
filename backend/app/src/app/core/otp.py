# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import hashlib
import hmac
import re
import secrets

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.rate_limit import incr_with_ttl, seconds_until

# `[0-9]`, not `\d`: on a str pattern `\d` also matches non-ASCII digits
# (Devanagari, full-width, …), which would store a second spelling of a number
# already on file and slip past every phone unique index.
_PHONE_RE = re.compile(r"^\+91[6-9][0-9]{9}$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(raw: str) -> str:
    """Accept Indian E.164 mobile numbers (`+91[6-9]XXXXXXXXX`).

    Strips whitespace and hyphens. Returns the canonical `+91XXXXXXXXXX`
    string. Raises InvalidPhoneNumber on anything else.
    """
    if not raw:
        raise InvalidPhoneNumber()
    cleaned = re.sub(r"[\s-]", "", raw)
    if not _PHONE_RE.match(cleaned):
        raise InvalidPhoneNumber()
    return cleaned


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(f"{settings.OTP_PEPPER}{code}".encode()).hexdigest()


def _key_code(identifier: str, namespace: str = "email") -> str:
    return f"otp:{namespace}:code:{identifier}"


def _key_cooldown(identifier: str, namespace: str = "email") -> str:
    return f"otp:{namespace}:cooldown:{identifier}"


def _key_hourly(identifier: str, namespace: str = "email") -> str:
    return f"otp:{namespace}:hourly:{identifier}"


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


class InvalidCode(Exception):
    pass


class CodeExpired(Exception):
    pass


class TooManyAttempts(Exception):
    pass


class InvalidPhoneNumber(Exception):
    pass


async def enforce_hourly_budget(
    identifier: str, redis: aioredis.Redis, *, namespace: str = "email"
) -> None:
    """Charge the per-identifier hourly OTP budget. Raises RateLimited past it.

    Split out of `request_otp` so the `PHONE_OTP_ENABLED=False` path — which
    issues no code at all — still pays the same toll. Those endpoints answer
    "is this phone already taken?" with a 409, which without a budget would
    be a free enumeration oracle. No resend cooldown is charged: the caller
    is not waiting on a code, so making them wait 60s would only stall a
    legitimate retry.
    """
    key = _key_hourly(identifier, namespace)
    if await incr_with_ttl(redis, key, 3600) > settings.OTP_MAX_PER_HOUR:
        raise RateLimited(retry_after=await seconds_until(redis, key))


def _key_distinct(identifier: str, namespace: str) -> str:
    return f"otp:{namespace}:distinct:{identifier}"


async def enforce_distinct_hourly_budget(
    identifier: str, member: str, redis: aioredis.Redis, *, namespace: str
) -> None:
    """Cap how many *distinct* members (e.g. phone numbers) one identifier
    may touch per hour. It limits breadth, unlike `enforce_hourly_budget`,
    which counts calls. A member already counted is free, so resends never
    eat the budget. The window opens with the first member. Raises
    RateLimited past OTP_MAX_PER_HOUR members. Two concurrent first-time
    members can overshoot by one; the cap is a brake, not a ledger."""
    key = _key_distinct(identifier, namespace)
    if await redis.sismember(key, member):  # type: ignore[misc]
        return
    if await redis.scard(key) >= settings.OTP_MAX_PER_HOUR:  # type: ignore[misc]
        raise RateLimited(retry_after=max(await seconds_until(redis, key), 1))
    await redis.sadd(key, member)  # type: ignore[misc]
    if await redis.ttl(key) < 0:
        await redis.expire(key, 3600)


async def request_otp(
    identifier: str, redis: aioredis.Redis, *, namespace: str = "email"
) -> str:
    """Store a new OTP in Redis. Returns the plaintext code for the caller to send."""
    cooldown = await seconds_until(redis, _key_cooldown(identifier, namespace))
    if cooldown > 0:
        raise RateLimited(retry_after=cooldown)

    await enforce_hourly_budget(identifier, redis, namespace=namespace)

    code = generate_code()
    pipe = redis.pipeline()
    pipe.hset(
        _key_code(identifier, namespace),
        mapping={"code_hash": hash_code(code), "attempts": "0"},
    )
    pipe.expire(_key_code(identifier, namespace), settings.OTP_TTL_SECONDS)
    pipe.set(
        _key_cooldown(identifier, namespace), "1", ex=settings.OTP_RESEND_COOLDOWN
    )
    await pipe.execute()
    return code


async def verify_otp(
    identifier: str, code: str, redis: aioredis.Redis, *, namespace: str = "email"
) -> bool:
    """Verify OTP code. Returns True on match; does NOT delete the key.

    Raises CodeExpired, InvalidCode, or TooManyAttempts on failure.
    Caller must call consume_otp_key() after successful auth.
    """
    data: dict[str, str] = await redis.hgetall(_key_code(identifier, namespace))  # type: ignore[misc]
    if not data:
        raise CodeExpired()

    if hmac.compare_digest(data.get("code_hash", ""), hash_code(code)):
        return True

    attempts = await redis.hincrby(_key_code(identifier, namespace), "attempts", 1)  # type: ignore[misc]
    if int(attempts) >= settings.OTP_MAX_ATTEMPTS:
        await redis.delete(_key_code(identifier, namespace))
        raise TooManyAttempts()
    raise InvalidCode()


async def consume_otp_key(
    identifier: str, redis: aioredis.Redis, *, namespace: str = "email"
) -> None:
    """Delete OTP code key and rate-limit counters after successful auth."""
    await redis.delete(
        _key_code(identifier, namespace),
        _key_cooldown(identifier, namespace),
        _key_hourly(identifier, namespace),
    )
