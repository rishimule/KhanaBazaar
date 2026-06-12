# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Authenticated seller self-service phone-change OTP endpoints.

A logged-in Approved seller proves control of a NEW phone number before an
identity change request that changes the phone can be submitted. Reuses the
shared OTP primitives under the ``seller_phone_change`` namespace and, on
verify, mints a short-lived ``phone_change_token`` bound to (user_id, phone).
"""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.otp import (
    CodeExpired,
    InvalidCode,
    InvalidPhoneNumber,
    RateLimited,
    TooManyAttempts,
    consume_otp_key,
    normalize_phone,
    request_otp,
    verify_otp,
)
from app.core.otp_delivery import deliver_phone_otp
from app.core.redis import get_redis
from app.core.security import (
    create_seller_phone_change_token,
    get_current_seller,
)
from app.core.sms import SMSSender, get_sms_sender
from app.core.whatsapp import WhatsAppSender, get_whatsapp_sender
from app.db.session import get_db_session
from app.models.base import User
from app.models.profile import SellerProfile
from app.schemas.sellers import (
    SellerSelfPhoneOtpRequestBody,
    SellerSelfPhoneOtpVerifyBody,
)

router = APIRouter()

_NAMESPACE = "seller_phone_change"


async def _profile_or_404(session: AsyncSession, seller: User) -> SellerProfile:
    profile = (
        await session.exec(
            select(SellerProfile).where(SellerProfile.user_id == seller.id)
        )
    ).first()
    if profile is None:
        raise HTTPException(
            status_code=404, detail={"error": "seller_profile_not_found"}
        )
    return profile


@router.post("/me/phone/otp/request")
async def request_phone_change_otp(
    body: SellerSelfPhoneOtpRequestBody,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
    sender: SMSSender = Depends(get_sms_sender),
    whatsapp_sender: WhatsAppSender | None = Depends(get_whatsapp_sender),
) -> dict:  # type: ignore[type-arg]
    profile = await _profile_or_404(session, seller)
    try:
        phone = normalize_phone(body.phone)
    except InvalidPhoneNumber:
        raise HTTPException(
            status_code=400, detail={"error": "invalid_phone"}
        ) from None
    if phone == profile.phone:
        raise HTTPException(
            status_code=400, detail={"error": "phone_unchanged"}
        )
    clash = (
        await session.exec(
            select(SellerProfile).where(
                SellerProfile.phone == phone,
                SellerProfile.id != profile.id,
            )
        )
    ).first()
    if clash is not None:
        raise HTTPException(status_code=409, detail={"error": "phone_taken"})
    try:
        code = await request_otp(phone, redis, namespace=_NAMESPACE)
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after": exc.retry_after},
        ) from exc
    await deliver_phone_otp(
        to=phone,
        template_name="otp_seller_phone",
        variables={"code": code},
        sms_text=(
            f"Your Khana Bazaar phone-change verification code is: {code}\n"
            "Expires in 10 minutes."
        ),
        sms_sender=sender,
        whatsapp_sender=whatsapp_sender,
    )
    return {"ok": True, "expires_in": settings.OTP_TTL_SECONDS}


@router.post("/me/phone/otp/verify")
async def verify_phone_change_otp(
    body: SellerSelfPhoneOtpVerifyBody,
    seller: User = Depends(get_current_seller),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:  # type: ignore[type-arg]
    try:
        phone = normalize_phone(body.phone)
    except InvalidPhoneNumber:
        raise HTTPException(
            status_code=400, detail={"error": "invalid_phone"}
        ) from None
    try:
        await verify_otp(phone, body.code, redis, namespace=_NAMESPACE)
    except CodeExpired:
        raise HTTPException(
            status_code=410, detail={"error": "code_expired_or_used"}
        ) from None
    except TooManyAttempts:
        raise HTTPException(
            status_code=429, detail={"error": "too_many_attempts"}
        ) from None
    except InvalidCode:
        raise HTTPException(
            status_code=400, detail={"error": "invalid_code"}
        ) from None
    await consume_otp_key(phone, redis, namespace=_NAMESPACE)
    assert seller.id is not None
    token = create_seller_phone_change_token(seller.id, phone)
    return {"phone_change_token": token}
