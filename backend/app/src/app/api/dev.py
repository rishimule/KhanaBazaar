# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Deploy-only dev OTP inbox endpoint. Disabled unless settings.EXPOSE_DEV_OTPS."""
import secrets as _secrets

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import settings
from app.core.dev_otp_log import recent_otps
from app.core.rate_limit import incr_with_ttl
from app.core.redis import get_redis

router = APIRouter()
_basic = HTTPBasic(auto_error=False)


async def _guard(
    redis: aioredis.Redis = Depends(get_redis),
    creds: HTTPBasicCredentials | None = Depends(_basic),
) -> None:
    # Feature hidden entirely when disabled — 404 regardless of credentials.
    if not settings.EXPOSE_DEV_OTPS:
        raise HTTPException(status_code=404)
    if creds is None:
        raise HTTPException(
            status_code=401,
            detail="authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    user_ok = _secrets.compare_digest(creds.username, settings.DEV_LOGS_USERNAME)
    pass_ok = _secrets.compare_digest(creds.password, settings.DEV_LOGS_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    count = await incr_with_ttl(redis, f"devotps:rl:{creds.username}", 60)
    if count > 120:
        raise HTTPException(status_code=429, detail="rate_limited")


@router.get("/otps", dependencies=[Depends(_guard)])
async def list_otps(
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:  # type: ignore[type-arg]
    return {"otps": await recent_otps(redis, limit=50)}
