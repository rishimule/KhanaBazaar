# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Deploy-only dev OTP inbox endpoint. Disabled unless settings.EXPOSE_DEV_OTPS."""
import secrets as _secrets

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import settings
from app.core.dev_otp_log import recent_otps
from app.core.rate_limit import incr_with_ttl
from app.core.redis import get_redis

router = APIRouter()
_basic = HTTPBasic(auto_error=False)

# Failed + successful attempts per client IP per minute. Legit polling is ~12/min
# (5s interval); this caps password brute-forcing well below that ceiling's abuse.
_RATE_LIMIT_PER_MIN = 60


async def _guard(
    request: Request,
    redis: aioredis.Redis = Depends(get_redis),
    creds: HTTPBasicCredentials | None = Depends(_basic),
) -> None:
    # Feature hidden entirely when disabled — 404 regardless of credentials.
    if not settings.EXPOSE_DEV_OTPS:
        raise HTTPException(status_code=404)
    # Throttle BEFORE evaluating credentials, keyed by client IP, so failed
    # guesses count toward the limit (brute-force protection on the password).
    client_ip = request.client.host if request.client else "unknown"
    count = await incr_with_ttl(redis, f"devotps:rl:{client_ip}", 60)
    if count > _RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="rate_limited")
    # A misconfigured deploy (flag on but creds unset) must never authorize on
    # empty client credentials — fail closed.
    if not settings.DEV_LOGS_USERNAME or not settings.DEV_LOGS_PASSWORD:
        raise HTTPException(status_code=503, detail="dev otp inbox not configured")
    if creds is None:
        raise HTTPException(
            status_code=401,
            detail="authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    # Encode to bytes: compare_digest raises TypeError on non-ASCII str operands.
    user_ok = _secrets.compare_digest(
        creds.username.encode("utf-8"), settings.DEV_LOGS_USERNAME.encode("utf-8")
    )
    pass_ok = _secrets.compare_digest(
        creds.password.encode("utf-8"), settings.DEV_LOGS_PASSWORD.encode("utf-8")
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("/otps", dependencies=[Depends(_guard)])
async def list_otps(
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:  # type: ignore[type-arg]
    return {"otps": await recent_otps(redis, limit=50)}
