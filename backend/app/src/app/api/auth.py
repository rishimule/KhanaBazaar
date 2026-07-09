# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.email import EmailSender, get_email_sender
from app.core.email_render import render_email
from app.core.otp import (
    CodeExpired,
    InvalidCode,
    InvalidPhoneNumber,
    RateLimited,
    TooManyAttempts,
    consume_otp_key,
    normalize_email,
    normalize_phone,
    request_otp,
    verify_otp,
)
from app.core.otp_delivery import deliver_phone_otp
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_seller_email_token,
    create_seller_signup_token,
    decode_seller_email_token,
    decode_seller_signup_token,
    get_current_user,
)
from app.core.sms import SMSSender, get_sms_sender
from app.core.whatsapp import WhatsAppSender, get_whatsapp_sender
from app.db.session import get_db_session
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import LanguageCode
from app.models.profile import CustomerProfile, SellerProfile
from app.schemas.address import address_from_payload
from app.schemas.sellers import (
    SellerPhoneOtpRequestBody,
    SellerPhoneOtpVerifyBody,
    SellerRegisterBody,
)
from app.services.consent import (
    get_effective_policy_version,
    has_accepted_current_policy,
    record_acceptance,
)
from app.services.profiles import compose_full_name, split_full_name

router = APIRouter()


class OTPRequestBody(BaseModel):
    email: EmailStr


class OTPVerifyBody(BaseModel):
    email: EmailStr
    code: str
    # Bounded so customer-controlled `full_name` cannot blow out the
    # `customer_welcome` email subject. CRLF is additionally stripped by
    # `core.email_render.render_email`.
    full_name: str | None = Field(default=None, max_length=120)
    accept_policies: bool = False


class UpdateLanguageBody(BaseModel):
    language: LanguageCode


class SellerOtpVerifyBody(BaseModel):
    email: EmailStr
    code: str


async def _profile_display(
    session: AsyncSession, user: User
) -> tuple[str | None, str | None]:
    """Resolve (full_name, avatar_url) from the user's role profile in one load.

    Admins have no avatar field; both are None for them (and for users without
    a profile yet).
    """
    if user.role == UserRole.Customer:
        customer_result = await session.exec(
            select(CustomerProfile).where(CustomerProfile.user_id == user.id)
        )
        profile = customer_result.first()
        if profile is None:
            return None, None
        return (
            compose_full_name(profile.first_name, profile.last_name),
            profile.avatar_url,
        )
    if user.role == UserRole.Seller:
        seller_result = await session.exec(
            select(SellerProfile).where(SellerProfile.user_id == user.id)
        )
        seller = seller_result.first()
        if seller is None:
            return None, None
        return (
            compose_full_name(seller.first_name, seller.last_name),
            seller.avatar_url,
        )
    return None, None


def _user_payload(
    user: User,
    full_name: str | None,
    avatar_url: str | None = None,
    needs_policy_acceptance: bool = False,
) -> dict:  # type: ignore[type-arg]
    payload = user.model_dump()
    payload["full_name"] = full_name
    payload["avatar_url"] = avatar_url
    payload["needs_policy_acceptance"] = needs_policy_acceptance
    return payload


@router.post("/otp/request")
async def otp_request(
    body: OTPRequestBody,
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
    sender: EmailSender = Depends(get_email_sender),
) -> dict:  # type: ignore[type-arg]
    email = normalize_email(str(body.email))
    try:
        code = await request_otp(email, redis)
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after": exc.retry_after},
        ) from exc
    ttl_minutes = settings.OTP_TTL_SECONDS // 60
    payload = render_email(
        "otp_login", {"code": code, "ttl_minutes": ttl_minutes}, lang="en"
    )
    try:
        await sender.send(
            to=email,
            subject=payload.subject,
            text=payload.text,
            html=payload.html,
            reply_to=settings.EMAIL_REPLY_TO,
        )
    except httpx.HTTPError:
        # Fall back to the Celery task so the request still returns 200 to the
        # user; the worker will retry transient Resend errors with backoff.
        from app.worker import send_otp_email_async

        send_otp_email_async.delay(email, code)
    # Best-effort WhatsApp mirror: an existing customer with a verified phone
    # gets the same code over WhatsApp too. Email stays the primary channel.
    if get_whatsapp_sender() is not None:
        user = (await session.exec(select(User).where(User.email == email))).first()
        if user is not None:
            profile = (
                await session.exec(
                    select(CustomerProfile).where(
                        CustomerProfile.user_id == user.id
                    )
                )
            ).first()
            if (
                profile is not None
                and profile.phone
                and profile.phone_verified_at is not None
            ):
                from app.services.order_emails import _safe_delay
                from app.worker import send_login_otp_whatsapp_async

                # Broker-safe dispatch: a Redis/broker outage must never break
                # the login 200 (the mirror is purely best-effort).
                _safe_delay(send_login_otp_whatsapp_async, code, profile.phone)
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
    avatar_url: str | None = None
    if user is None:
        if not body.full_name:
            return {"access_token": None, "token_type": None, "user": None, "needs_name": True}
        effective = await get_effective_policy_version(session)
        if effective is not None and not body.accept_policies:
            raise HTTPException(
                status_code=400, detail={"error": "policy_acceptance_required"}
            )
        first_name, last_name = split_full_name(body.full_name)
        user = User(email=email, role=UserRole.Customer)
        session.add(user)
        await session.flush()
        assert user.id is not None
        profile = CustomerProfile(user_id=user.id, first_name=first_name, last_name=last_name)
        session.add(profile)
        await record_acceptance(session, user.id)
        await session.commit()
        await session.refresh(user)
        full_name = compose_full_name(first_name, last_name)
        from app.services.seller_emails import dispatch_customer_welcome

        if user.id is not None:
            dispatch_customer_welcome(user.id)
    else:
        full_name, avatar_url = await _profile_display(session, user)

    await consume_otp_key(email, redis)
    token = create_access_token(user)
    assert user.id is not None
    needs = not await has_accepted_current_policy(session, user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _user_payload(user, full_name, avatar_url, needs_policy_acceptance=needs),
        "needs_name": False,
    }


@router.get("/me")
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    full_name, avatar_url = await _profile_display(session, user)
    assert user.id is not None
    needs = not await has_accepted_current_policy(session, user.id)
    return _user_payload(user, full_name, avatar_url, needs_policy_acceptance=needs)


@router.post("/policy/accept")
async def accept_policy(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    assert user.id is not None
    version = await record_acceptance(session, user.id)
    await session.commit()
    return {"accepted": True, "version": version}


@router.patch("/me/language", status_code=204)
async def update_me_language(
    body: UpdateLanguageBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    user.preferred_language = body.language.value
    session.add(user)
    await session.commit()


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
    email_token = create_seller_email_token(email)
    return {"email_token": email_token}


@router.post("/seller/register")
async def seller_register(
    body: SellerRegisterBody,
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    from app.services.seller_services import (
        replace_profile_services,
        validate_service_ids,
    )

    email, phone = decode_seller_signup_token(body.signup_token)

    effective = await get_effective_policy_version(session)
    if effective is not None and not body.accept_policies:
        raise HTTPException(
            status_code=400, detail={"error": "policy_acceptance_required"}
        )

    user_exists = await session.exec(select(User).where(User.email == email))
    if user_exists.first():
        raise HTTPException(
            status_code=409, detail={"error": "email_already_registered"}
        )
    phone_exists = await session.exec(
        select(SellerProfile).where(SellerProfile.phone == phone)
    )
    if phone_exists.first():
        raise HTTPException(
            status_code=409, detail={"error": "phone_already_registered"}
        )

    try:
        valid_ids = await validate_service_ids(session, body.service_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    first_name, last_name = split_full_name(body.full_name)
    user = User(email=email, role=UserRole.Seller)
    session.add(user)
    await session.flush()
    assert user.id is not None
    await record_acceptance(session, user.id)

    address = Address(**address_from_payload(body.address))
    session.add(address)
    await session.flush()

    profile = SellerProfile(
        user_id=user.id,
        first_name=first_name,
        last_name=last_name,
        business_name=body.business_name,
        phone=phone,
        gst_number=body.gst_number or None,
        fssai_license=body.fssai_license or None,
        bank_account_number=body.bank_account_number or None,
        bank_ifsc=body.bank_ifsc or None,
        business_address_id=address.id,
    )
    session.add(profile)
    await session.flush()
    await replace_profile_services(session, profile, valid_ids)

    # Bind referral attribution when the wizard was entered via an invite link,
    # in the SAME transaction as the seller creation. Best-effort: an invalid or
    # mismatched token is ignored and never blocks seller signup. Match on the
    # token's email OR phone so phone-only seller invites are still credited.
    bound_referral = None
    if body.referral_invite_token and user.id is not None:
        from app.core.security import decode_referral_invite_token
        from app.services.referrals import bind_seller_referral

        try:
            claims = decode_referral_invite_token(body.referral_invite_token)
        except HTTPException:
            claims = None
        if (
            claims
            and claims["target_role"] == "seller"
            and (claims.get("email") == email or claims.get("phone") == phone)
        ):
            bound_referral = await bind_seller_referral(
                session,
                referral_id=int(str(claims["referral_id"])),
                user_id=int(user.id),
            )

    await session.commit()
    await session.refresh(user)
    await session.refresh(profile)

    if profile.id is not None:
        from app.services.seller_emails import (
            dispatch_seller_application_submitted,
        )

        dispatch_seller_application_submitted(profile.id)

    token = create_access_token(user)
    full_name = compose_full_name(first_name, last_name)
    response = {
        "access_token": token,
        "token_type": "bearer",
        "user": _user_payload(user, full_name),
    }

    # Post-commit, best-effort referrer notification, LAST (it commits its own
    # write, which expires session objects). Never blocks/undoes signup.
    if bound_referral is not None:
        from app.services.referrals import notify_referral_event

        await session.refresh(bound_referral)
        await notify_referral_event(session, referral=bound_referral, event="activated")

    return response


@router.post("/seller/phone/otp/request")
async def seller_phone_otp_request(
    body: SellerPhoneOtpRequestBody,
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
    sender: SMSSender = Depends(get_sms_sender),
    whatsapp_sender: WhatsAppSender | None = Depends(get_whatsapp_sender),
) -> dict:  # type: ignore[type-arg]
    decode_seller_email_token(body.email_token)

    try:
        phone = normalize_phone(body.phone)
    except InvalidPhoneNumber:
        raise HTTPException(
            status_code=400, detail={"error": "invalid_phone"}
        ) from None

    existing = await session.exec(
        select(SellerProfile).where(SellerProfile.phone == phone)
    )
    if existing.first():
        raise HTTPException(
            status_code=409, detail={"error": "phone_already_registered"}
        )

    try:
        code = await request_otp(phone, redis, namespace="phone")
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
            f"Your {settings.COMPANY_NAME} seller verification code is: {code}\n"
            "Expires in 10 minutes."
        ),
        sms_sender=sender,
        whatsapp_sender=whatsapp_sender,
    )
    return {"ok": True, "expires_in": settings.OTP_TTL_SECONDS}


@router.post("/seller/phone/otp/verify")
async def seller_phone_otp_verify(
    body: SellerPhoneOtpVerifyBody,
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:  # type: ignore[type-arg]
    email = decode_seller_email_token(body.email_token)

    try:
        phone = normalize_phone(body.phone)
    except InvalidPhoneNumber:
        raise HTTPException(
            status_code=400, detail={"error": "invalid_phone"}
        ) from None

    try:
        await verify_otp(phone, body.code, redis, namespace="phone")
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

    await consume_otp_key(phone, redis, namespace="phone")
    signup_token = create_seller_signup_token(email, phone)
    return {"signup_token": signup_token}
