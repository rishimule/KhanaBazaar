# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Deploy-only mirror of plaintext OTP codes into Redis.

Enabled by settings.EXPOSE_DEV_OTPS. Lets a private credit-funded deployment
recover login codes without a real email provider, via GET /api/v1/dev/otps.
NEVER enable on a real user-facing deployment.
"""
import json
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.core.config import settings

_KEY = "dev:otps"
_MAX_ENTRIES = 100
_TTL_SECONDS = 3600


async def record_otp(
    redis: aioredis.Redis, identifier: str, code: str, *, namespace: str = "email"
) -> None:
    """Push a plaintext OTP entry onto the dev inbox list. No-op when disabled."""
    if not settings.EXPOSE_DEV_OTPS:
        return
    entry = json.dumps(
        {
            "to": identifier,
            "code": code,
            "purpose": namespace,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    pipe = redis.pipeline()
    pipe.lpush(_KEY, entry)
    pipe.ltrim(_KEY, 0, _MAX_ENTRIES - 1)
    pipe.expire(_KEY, _TTL_SECONDS)
    await pipe.execute()


async def recent_otps(redis: aioredis.Redis, limit: int = 50) -> list[dict]:  # type: ignore[type-arg]
    """Return recent OTP entries, newest first."""
    raw: list[str] = await redis.lrange(_KEY, 0, limit - 1)  # type: ignore[misc]
    return [json.loads(item) for item in raw]
