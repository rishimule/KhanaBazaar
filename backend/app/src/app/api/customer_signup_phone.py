# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pre-account phone proof for customer signup (spec 2026-10-08).

A new customer gives a phone number before their account exists. These two
endpoints turn that number into a short-lived `phone_token`, which
`POST /auth/otp/verify` (new email) and `POST /referrals/accept` require.

Three things differ from the older phone chains on purpose:
- `request` is gated by the *live email code*, so an anonymous caller can
  neither trigger a send nor learn whether a number is registered.
- The phone code is keyed by phone + requesting email, so a stranger who
  knows the number alone can't burn its attempts.
- `verify` never short-circuits on PHONE_OTP_ENABLED. No client older than
  the flag exists for it, and a code-free mint would hand out tokens for any
  number, skipping the uniqueness check and budgets `request` charges.
"""
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.otp import (
    CodeExpired,
    InvalidCode,
    InvalidPhoneNumber,
    RateLimited,
    TooManyAttempts,
    consume_otp_key,
    enforce_distinct_hourly_budget,
    enforce_hourly_budget,
    normalize_email,
    normalize_phone,
    request_otp,
    verify_otp,
)
from app.core.otp_delivery import deliver_phone_otp
from app.core.redis import get_redis
from app.core.security import create_customer_signup_phone_token
from app.core.sms import SMSSender, get_sms_sender
from app.core.whatsapp import WhatsAppSender, get_whatsapp_sender
from app.db.session import get_db_session
from app.services.customer_signup import (
    budget_identity,
    customer_phone_taken,
    email_registered,
)

router = APIRouter()

# The phone code (keyed by phone + email) and the per-phone hourly budget
# (keyed by phone alone) live here.
_PHONE_NAMESPACE = "customer_signup_phone"
# Breadth cap: how many distinct numbers one email may probe or text an hour.
_EMAIL_NAMESPACE = "customer_signup_email"


class CustomerSignupPhoneOtpRequestBody(BaseModel):
    email: EmailStr
    # The login code the customer just verified; still live (not consumed).
    email_code: str = Field(max_length=12)
    phone: str = Field(max_length=20)


class CustomerSignupPhoneOtpVerifyBody(BaseModel):
    email: EmailStr
    phone: str = Field(max_length=20)
    # The code sent to the phone.
    code: str = Field(max_length=12)


def _pair(phone: str, email: str) -> str:
    return f"{phone}:{email}"


def _rate_limited(exc: RateLimited) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={"error": "rate_limited", "retry_after": exc.retry_after},
    )


def _code_error(exc: Exception) -> HTTPException:
    """The codes /auth/otp/verify uses for a failed code check."""
    if isinstance(exc, CodeExpired):
        return HTTPException(status_code=410, detail={"error": "code_expired_or_used"})
    if isinstance(exc, TooManyAttempts):
        return HTTPException(status_code=429, detail={"error": "too_many_attempts"})
    return HTTPException(status_code=400, detail={"error": "invalid_code"})


def _phone_or_400(raw: str) -> str:
    try:
        return normalize_phone(raw)
    except InvalidPhoneNumber:
        raise HTTPException(
            status_code=400, detail={"error": "invalid_phone"}
        ) from None


@router.post("/customer/phone/otp/request")
async def customer_signup_phone_otp_request(
    body: CustomerSignupPhoneOtpRequestBody,
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
    sender: SMSSender = Depends(get_sms_sender),
    whatsapp_sender: WhatsAppSender | None = Depends(get_whatsapp_sender),
) -> dict[str, object]:
    email = normalize_email(str(body.email))
    # Gate first: without the live email code a caller learns nothing about
    # phones and cannot trigger a send. Not consumed — account creation
    # verifies it again and consumes it.
    try:
        await verify_otp(email, body.email_code, redis)
    except (CodeExpired, InvalidCode, TooManyAttempts) as exc:
        raise _code_error(exc) from None
    if await email_registered(session, email):
        raise HTTPException(
            status_code=409, detail={"error": "email_already_registered"}
        )
    phone = _phone_or_400(body.phone)
    # Charged before the uniqueness check, so every "is this taken?" probe
    # costs budget; a malformed number above costs nothing (it leaks nothing).
    try:
        await enforce_distinct_hourly_budget(
            budget_identity(email), phone, redis, namespace=_EMAIL_NAMESPACE
        )
    except RateLimited as exc:
        raise _rate_limited(exc) from exc
    if await customer_phone_taken(session, phone):
        raise HTTPException(status_code=409, detail={"error": "phone_already_in_use"})

    try:
        # Per phone, across every email: nobody texts one number more than
        # OTP_MAX_PER_HOUR times an hour, and the trust path pays the same.
        await enforce_hourly_budget(phone, redis, namespace=_PHONE_NAMESPACE)
    except RateLimited as exc:
        raise _rate_limited(exc) from exc

    if not settings.PHONE_OTP_ENABLED:
        # No transport to deliver a code with: take the number on trust and
        # hand back the token a verified code would have earned.
        return {
            "ok": True,
            "otp_required": False,
            "phone_token": create_customer_signup_phone_token(email, phone),
        }

    try:
        code = await request_otp(
            _pair(phone, email), redis, namespace=_PHONE_NAMESPACE
        )
    except RateLimited as exc:
        raise _rate_limited(exc) from exc
    await deliver_phone_otp(
        to=phone,
        template_name="otp_customer_signup",
        variables={"code": code},
        sms_text=(
            f"Your {settings.COMPANY_NAME} verification code is: {code}\n"
            f"Expires in {settings.OTP_TTL_SECONDS // 60} minutes."
        ),
        sms_sender=sender,
        whatsapp_sender=whatsapp_sender,
    )
    return {
        "ok": True,
        "otp_required": True,
        "expires_in": settings.OTP_TTL_SECONDS,
    }


@router.post("/customer/phone/otp/verify")
async def customer_signup_phone_otp_verify(
    body: CustomerSignupPhoneOtpVerifyBody,
    redis: aioredis.Redis = Depends(get_redis),
) -> dict[str, object]:
    email = normalize_email(str(body.email))
    phone = _phone_or_400(body.phone)
    # No PHONE_OTP_ENABLED short-circuit (module docstring). A code sent
    # before the flag flipped off still verifies, since this never reads it.
    try:
        await verify_otp(
            _pair(phone, email), body.code, redis, namespace=_PHONE_NAMESPACE
        )
    except (CodeExpired, InvalidCode, TooManyAttempts) as exc:
        raise _code_error(exc) from None
    await consume_otp_key(_pair(phone, email), redis, namespace=_PHONE_NAMESPACE)
    return {"phone_token": create_customer_signup_phone_token(email, phone)}
