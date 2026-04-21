import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.email import EmailSender, get_email_sender
from app.core.otp import (
    CodeExpired,
    InvalidCode,
    RateLimited,
    TooManyAttempts,
    consume_otp_key,
    normalize_email,
    request_otp,
    verify_otp,
)
from app.core.redis import get_redis
from app.core.security import create_access_token, get_current_user
from app.db.session import get_db_session
from app.models.base import User, UserRole

router = APIRouter()


class OTPRequestBody(BaseModel):
    email: EmailStr


class OTPVerifyBody(BaseModel):
    email: EmailStr
    code: str
    full_name: str | None = None


@router.post("/otp/request")
async def otp_request(
    body: OTPRequestBody,
    redis: aioredis.Redis = Depends(get_redis),
    sender: EmailSender = Depends(get_email_sender),
) -> dict:  # type: ignore[type-arg]
    try:
        code = await request_otp(str(body.email), redis)
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after": exc.retry_after},
        ) from exc
    await sender.send(
        to=str(body.email),
        subject="Your Khana Bazaar login code",
        text=f"Your one-time login code is: {code}\n\nThis code expires in 10 minutes.",
    )
    return {"ok": True, "expires_in": settings.OTP_TTL_SECONDS}


@router.post("/otp/verify")
async def otp_verify(
    body: OTPVerifyBody,
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:  # type: ignore[type-arg]
    email = normalize_email(str(body.email))

    try:
        await verify_otp(email, body.code, redis)
    except CodeExpired:
        raise HTTPException(status_code=410, detail={"error": "code_expired_or_used"}) from None
    except TooManyAttempts:
        raise HTTPException(status_code=429, detail={"error": "too_many_attempts"}) from None
    except InvalidCode:
        raise HTTPException(status_code=400, detail={"error": "invalid_code"}) from None

    result = await session.exec(select(User).where(User.email == email))
    user = result.first()

    if user is None:
        if not body.full_name:
            return {"access_token": None, "token_type": None, "user": None, "needs_name": True}
        user = User(email=email, full_name=body.full_name.strip(), role=UserRole.Customer)
        session.add(user)
        await session.commit()
        await session.refresh(user)

    await consume_otp_key(email, redis)
    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user.model_dump(),
        "needs_name": False,
    }


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:  # type: ignore[type-arg]
    return user.model_dump()
