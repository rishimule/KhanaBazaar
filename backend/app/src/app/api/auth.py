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
from app.core.security import (
    create_access_token,
    create_email_verification_token,
    decode_email_verification_token,
    get_current_user,
)
from app.db.session import get_db_session
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import CustomerProfile, SellerProfile
from app.schemas.address import address_from_payload
from app.schemas.sellers import SellerRegisterBody
from app.services.profiles import compose_full_name, split_full_name

router = APIRouter()


class OTPRequestBody(BaseModel):
    email: EmailStr


class OTPVerifyBody(BaseModel):
    email: EmailStr
    code: str
    full_name: str | None = None


class SellerOtpVerifyBody(BaseModel):
    email: EmailStr
    code: str


async def _full_name_for_user(session: AsyncSession, user: User) -> str | None:
    if user.role == UserRole.Customer:
        customer_result = await session.exec(
            select(CustomerProfile).where(CustomerProfile.user_id == user.id)
        )
        profile = customer_result.first()
        if profile is None:
            return None
        return compose_full_name(profile.first_name, profile.last_name)
    if user.role == UserRole.Seller:
        seller_result = await session.exec(
            select(SellerProfile).where(SellerProfile.user_id == user.id)
        )
        seller = seller_result.first()
        if seller is None:
            return None
        return compose_full_name(seller.first_name, seller.last_name)
    return None


def _user_payload(user: User, full_name: str | None) -> dict:  # type: ignore[type-arg]
    payload = user.model_dump()
    payload["full_name"] = full_name
    return payload


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

    full_name: str | None
    if user is None:
        if not body.full_name:
            return {"access_token": None, "token_type": None, "user": None, "needs_name": True}
        first_name, last_name = split_full_name(body.full_name)
        user = User(email=email, role=UserRole.Customer)
        session.add(user)
        await session.flush()
        assert user.id is not None
        profile = CustomerProfile(user_id=user.id, first_name=first_name, last_name=last_name)
        session.add(profile)
        await session.commit()
        await session.refresh(user)
        full_name = compose_full_name(first_name, last_name)
    else:
        full_name = await _full_name_for_user(session, user)

    await consume_otp_key(email, redis)
    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _user_payload(user, full_name),
        "needs_name": False,
    }


@router.get("/me")
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    full_name = await _full_name_for_user(session, user)
    return _user_payload(user, full_name)


@router.post("/seller/otp/verify")
async def seller_otp_verify(
    body: SellerOtpVerifyBody,
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

    await consume_otp_key(email, redis)
    email_token = create_email_verification_token(email)
    return {"email_token": email_token}


@router.post("/seller/register")
async def seller_register(
    body: SellerRegisterBody,
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    email = decode_email_verification_token(body.email_token)

    result = await session.exec(select(User).where(User.email == email))
    if result.first():
        raise HTTPException(status_code=409, detail={"error": "email_already_registered"})

    first_name, last_name = split_full_name(body.full_name)
    user = User(email=email, role=UserRole.Seller)
    session.add(user)
    await session.flush()

    address = Address(**address_from_payload(body.address))
    session.add(address)
    await session.flush()

    profile = SellerProfile(
        user_id=user.id,
        first_name=first_name,
        last_name=last_name,
        business_name=body.business_name,
        business_category=body.business_category,
        phone=body.phone,
        gst_number=body.gst_number,
        fssai_license=body.fssai_license,
        bank_account_number=body.bank_account_number,
        bank_ifsc=body.bank_ifsc,
        business_address_id=address.id,
    )
    session.add(profile)
    await session.commit()
    await session.refresh(user)

    token = create_access_token(user)
    full_name = compose_full_name(first_name, last_name)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _user_payload(user, full_name),
    }
