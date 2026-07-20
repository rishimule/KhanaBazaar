# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
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
    normalize_phone,
    request_otp,
    verify_otp,
)
from app.core.rate_limit import incr_with_ttl
from app.core.redis import get_redis
from app.core.security import get_current_customer
from app.core.sms import SMSSender, get_sms_sender
from app.db.session import get_db_session
from app.models.address import Address
from app.models.base import AccountStatus, User
from app.models.profile import CustomerAddress, CustomerProfile
from app.schemas.address import address_from_payload, address_to_payload
from app.schemas.customer_stats import CustomerStatsResponse
from app.schemas.customers import (
    AccountDeactivateBody,
    AccountDeleteBody,
    CustomerAddressRead,
    CustomerAddressWrite,
    CustomerPreferencesUpdate,
    CustomerProfileRead,
    CustomerProfileUpdate,
)
from app.services.account_emails import dispatch_account_status_email
from app.services.account_lifecycle import (
    InvalidTransition,
    OpenObligations,
    transition,
)
from app.services.customer_stats import compute_stats
from app.services.image_processing import ImageValidationError
from app.services.profile_avatars import delete_blob, process_and_store

router = APIRouter()


async def _customer_profile_for_user(
    session: AsyncSession,
    user_id: int,
) -> CustomerProfile:
    result = await session.exec(
        select(CustomerProfile).where(CustomerProfile.user_id == user_id)
    )
    profile = result.first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return profile


async def _customer_addresses(
    session: AsyncSession,
    customer_profile_id: int,
) -> list[CustomerAddress]:
    result = await session.exec(
        select(CustomerAddress)
        .where(CustomerAddress.customer_profile_id == customer_profile_id)
        .options(selectinload(CustomerAddress.address))  # type: ignore[arg-type]
        .order_by(desc(CustomerAddress.is_default), CustomerAddress.id)  # type: ignore[arg-type]
    )
    return list(result.all())


async def _profile_response(
    session: AsyncSession,
    user: User,
    profile: CustomerProfile,
) -> CustomerProfileRead:
    assert user.id is not None
    assert profile.id is not None
    addresses = await _customer_addresses(session, profile.id)
    return CustomerProfileRead(
        user_id=user.id,
        email=user.email,
        first_name=profile.first_name,
        last_name=profile.last_name,
        phone=profile.phone,
        date_of_birth=profile.date_of_birth,
        # User.preferred_language is the single source of truth (also updated by
        # /auth/me/language from the navbar switcher, which does not touch the
        # profile column). Read it here so the account page always shows the
        # language the app actually renders.
        preferred_language=user.preferred_language,
        marketing_opt_in=profile.marketing_opt_in,
        notify_order_email=profile.notify_order_email,
        notify_order_sms=profile.notify_order_sms,
        phone_verified_at=profile.phone_verified_at,
        avatar_url=profile.avatar_url,
        account_status=user.account_status.value,
        addresses=[
            CustomerAddressRead(
                id=customer_address.id,
                label=customer_address.label,
                is_default=customer_address.is_default,
                address=address_to_payload(customer_address.address),
            )
            for customer_address in addresses
            if customer_address.id is not None
        ],
    )


async def _owned_customer_address(
    session: AsyncSession,
    profile: CustomerProfile,
    customer_address_id: int,
) -> CustomerAddress:
    assert profile.id is not None
    result = await session.exec(
        select(CustomerAddress)
        .where(
            CustomerAddress.id == customer_address_id,
            CustomerAddress.customer_profile_id == profile.id,
        )
        .options(selectinload(CustomerAddress.address))  # type: ignore[arg-type]
    )
    customer_address = result.first()
    if customer_address is None:
        raise HTTPException(status_code=404, detail="Customer address not found")
    return customer_address


async def _clear_default_addresses(
    session: AsyncSession,
    customer_profile_id: int,
) -> None:
    addresses = await _customer_addresses(session, customer_profile_id)
    cleared = False
    for customer_address in addresses:
        if customer_address.is_default:
            customer_address.is_default = False
            session.add(customer_address)
            cleared = True
    if cleared:
        await session.flush()


@router.get("/me", response_model=CustomerProfileRead)
async def get_customer_profile(
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    return await _profile_response(session, current_user, profile)


@router.get("/me/stats", response_model=CustomerStatsResponse)
async def customer_stats(
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerStatsResponse:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    assert profile.id is not None
    return await compute_stats(session, profile.id)


@router.patch("/me", response_model=CustomerProfileRead)
async def update_customer_profile(
    body: CustomerProfileUpdate,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)

    if body.first_name is not None:
        profile.first_name = body.first_name
    if "last_name" in body.model_fields_set:
        profile.last_name = body.last_name
    if "phone" in body.model_fields_set:
        # Editing the phone via the profile form invalidates any prior
        # verification — the user must re-verify the new number through
        # the OTP flow before it's marked verified again.
        if body.phone != profile.phone:
            profile.phone_verified_at = None
        profile.phone = body.phone
    if "date_of_birth" in body.model_fields_set:
        profile.date_of_birth = body.date_of_birth

    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return await _profile_response(session, current_user, profile)


@router.post("/me/avatar", response_model=CustomerProfileRead)
async def upload_customer_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    assert profile.id is not None
    raw = await file.read()
    try:
        url, key = await process_and_store(raw, "customer", profile.id)
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    old_key = profile.avatar_storage_key
    profile.avatar_url = url
    profile.avatar_storage_key = key
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    if old_key and old_key != key:
        await delete_blob(old_key)
    return await _profile_response(session, current_user, profile)


@router.delete("/me/avatar", response_model=CustomerProfileRead)
async def delete_customer_avatar(
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    old_key = profile.avatar_storage_key
    profile.avatar_url = None
    profile.avatar_storage_key = None
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    await delete_blob(old_key)
    return await _profile_response(session, current_user, profile)


@router.patch("/me/preferences", response_model=CustomerProfileRead)
async def update_customer_preferences(
    body: CustomerPreferencesUpdate,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    if "preferred_language" in body.model_fields_set:
        lang = body.preferred_language.value if body.preferred_language else None
        profile.preferred_language = lang
        # Mirror onto User.preferred_language, the single source of truth read by
        # /auth/me (locale seeding), the worker (order/notification copy), and the
        # profile response below. The User column is NOT NULL, so a cleared
        # preference falls back to "en".
        resolved = lang or "en"
        # Persist to the session-attached row (identity-map hit in prod).
        db_user = await session.get(User, current_user.id)
        if db_user is not None:
            db_user.preferred_language = resolved
            session.add(db_user)
        # Keep the response (built from current_user) in sync: in prod this is the
        # same identity-mapped instance as db_user; under the detached test
        # override it mirrors the persisted value so the response is consistent.
        current_user.preferred_language = resolved
    if "marketing_opt_in" in body.model_fields_set and body.marketing_opt_in is not None:
        profile.marketing_opt_in = body.marketing_opt_in
    if (
        "notify_order_email" in body.model_fields_set
        and body.notify_order_email is not None
    ):
        profile.notify_order_email = body.notify_order_email
    if (
        "notify_order_sms" in body.model_fields_set
        and body.notify_order_sms is not None
    ):
        profile.notify_order_sms = body.notify_order_sms
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return await _profile_response(session, current_user, profile)


class SupportMessage(BaseModel):
    subject: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)


SUPPORT_RATE_LIMIT_PER_HOUR = 5


@router.post("/me/support", status_code=202)
async def send_support_message(
    body: SupportMessage,
    current_user: User = Depends(get_current_customer),
) -> dict[str, bool]:
    from app.worker import send_support_email

    assert current_user.id is not None
    redis = await get_redis()
    sent = await incr_with_ttl(redis, f"support:hourly:{current_user.id}", 3600)
    if sent > SUPPORT_RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited"},
        )
    # SECURITY: reply_to in send_support_email is derived from the
    # authenticated user's email, NOT from request body. Do not switch this
    # to `body.email` without re-evaluating reply-to spoofing.
    send_support_email.delay(current_user.email, body.subject, body.message)
    return {"queued": True}


class PhoneOtpRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=20)


class PhoneOtpVerify(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    code: str = Field(min_length=6, max_length=6)


async def _phone_in_use_by_other(
    session: AsyncSession, phone: str, current_profile_id: int
) -> bool:
    result = await session.exec(
        select(CustomerProfile).where(
            CustomerProfile.phone == phone,
            CustomerProfile.id != current_profile_id,  # type: ignore[arg-type]
        )
    )
    return result.first() is not None


@router.post("/me/phone/otp/request")
async def request_customer_phone_otp(
    body: PhoneOtpRequest,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
    sms_sender: SMSSender = Depends(get_sms_sender),
) -> dict[str, bool]:
    assert current_user.id is not None
    try:
        phone = normalize_phone(body.phone)
    except InvalidPhoneNumber as exc:
        raise HTTPException(
            status_code=422, detail={"error": "phone_invalid"}
        ) from exc
    profile = await _customer_profile_for_user(session, current_user.id)
    assert profile.id is not None
    if await _phone_in_use_by_other(session, phone, profile.id):
        raise HTTPException(
            status_code=409, detail={"error": "phone_already_in_use"}
        )
    redis = await get_redis()
    try:
        code = await request_otp(phone, redis, namespace="customer_phone")
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after": exc.retry_after},
        ) from exc
    await sms_sender.send(phone, f"Your verification code is {code}")
    return {"sent": True}


@router.post("/me/phone/otp/verify", response_model=CustomerProfileRead)
async def verify_customer_phone_otp(
    body: PhoneOtpVerify,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    try:
        phone = normalize_phone(body.phone)
    except InvalidPhoneNumber as exc:
        raise HTTPException(
            status_code=422, detail={"error": "phone_invalid"}
        ) from exc
    profile = await _customer_profile_for_user(session, current_user.id)
    assert profile.id is not None
    if await _phone_in_use_by_other(session, phone, profile.id):
        raise HTTPException(
            status_code=409, detail={"error": "phone_already_in_use"}
        )
    redis = await get_redis()
    try:
        await verify_otp(phone, body.code, redis, namespace="customer_phone")
    except (CodeExpired, InvalidCode, TooManyAttempts) as exc:
        raise HTTPException(
            status_code=422, detail={"error": "otp_invalid"}
        ) from exc
    profile.phone = phone
    profile.phone_verified_at = datetime.now(timezone.utc)
    session.add(profile)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail={"error": "phone_already_in_use"}
        ) from exc
    await session.refresh(profile)
    await consume_otp_key(phone, redis, namespace="customer_phone")
    return await _profile_response(session, current_user, profile)


@router.post("/me/deactivate")
async def deactivate_account(
    body: AccountDeactivateBody,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Reversible self-deactivation. Blocked while open obligations exist."""
    assert current_user.id is not None
    uid = current_user.id  # capture before commit; commit expires ORM attributes
    try:
        await transition(
            session, user_id=uid, to_status=AccountStatus.deactivated,
            actor_user_id=None, actor_role="customer", reason=body.reason,
            enforce_obligations=True,
        )
    except OpenObligations as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "open_obligations",
                "open_orders": exc.open_orders,
                "credit_accounts": exc.credit_accounts,
            },
        ) from exc
    except InvalidTransition as exc:
        raise HTTPException(
            status_code=409, detail={"error": "invalid_transition"}
        ) from exc
    await session.commit()
    dispatch_account_status_email(uid, "account_deactivated")
    return {"status": "deactivated"}


@router.post("/me/delete/otp/request")
async def request_account_delete_otp(
    current_user: User = Depends(get_current_customer),
    sender: EmailSender = Depends(get_email_sender),
) -> dict[str, bool]:
    """Send a fresh OTP to the account email to confirm a terminal delete."""
    redis = await get_redis()
    try:
        code = await request_otp(
            current_user.email, redis, namespace="account_delete"
        )
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after": exc.retry_after},
        ) from exc
    ttl_minutes = settings.OTP_TTL_SECONDS // 60
    payload = render_email(
        "otp_login", {"code": code, "ttl_minutes": ttl_minutes}, lang="en"
    )
    await sender.send(
        to=current_user.email, subject=payload.subject, text=payload.text
    )
    return {"sent": True}


@router.post("/me/delete")
async def delete_account(
    body: AccountDeleteBody,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Terminal soft-delete after OTP confirmation. Blocked while open
    obligations exist; only an admin can restore afterwards."""
    assert current_user.id is not None
    uid = current_user.id  # capture before commit; commit expires ORM attributes
    email = current_user.email
    redis = await get_redis()
    try:
        await verify_otp(email, body.code, redis, namespace="account_delete")
    except (CodeExpired, InvalidCode, TooManyAttempts) as exc:
        raise HTTPException(status_code=422, detail={"error": "otp_invalid"}) from exc
    try:
        await transition(
            session, user_id=uid, to_status=AccountStatus.deleted,
            actor_user_id=None, actor_role="customer", reason=body.reason,
            enforce_obligations=True,
        )
    except OpenObligations as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "open_obligations",
                "open_orders": exc.open_orders,
                "credit_accounts": exc.credit_accounts,
            },
        ) from exc
    except InvalidTransition as exc:
        raise HTTPException(
            status_code=409, detail={"error": "invalid_transition"}
        ) from exc
    await session.commit()
    await consume_otp_key(email, redis, namespace="account_delete")
    dispatch_account_status_email(uid, "account_deleted")
    return {"status": "deleted"}


@router.post("/me/addresses", response_model=CustomerProfileRead)
async def create_customer_address(
    body: CustomerAddressWrite,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    assert profile.id is not None
    if body.is_default:
        await _clear_default_addresses(session, profile.id)

    address = Address(**address_from_payload(body.address))
    session.add(address)
    await session.flush()
    assert address.id is not None

    customer_address = CustomerAddress(
        customer_profile_id=profile.id,
        address_id=address.id,
        label=body.label,
        is_default=body.is_default,
    )
    session.add(customer_address)
    await session.commit()
    await session.refresh(profile)
    return await _profile_response(session, current_user, profile)


@router.put("/me/addresses/{customer_address_id}", response_model=CustomerProfileRead)
async def update_customer_address(
    customer_address_id: int,
    body: CustomerAddressWrite,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    customer_address = await _owned_customer_address(session, profile, customer_address_id)

    if body.is_default:
        assert profile.id is not None
        await _clear_default_addresses(session, profile.id)

    customer_address.label = body.label
    customer_address.is_default = body.is_default
    for key, value in address_from_payload(body.address).items():
        setattr(customer_address.address, key, value)

    session.add(customer_address.address)
    session.add(customer_address)
    await session.commit()
    await session.refresh(profile)
    return await _profile_response(session, current_user, profile)


@router.delete("/me/addresses/{customer_address_id}", response_model=CustomerProfileRead)
async def delete_customer_address(
    customer_address_id: int,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    customer_address = await _owned_customer_address(session, profile, customer_address_id)
    address = customer_address.address

    await session.delete(customer_address)
    await session.delete(address)
    await session.commit()
    await session.refresh(profile)
    return await _profile_response(session, current_user, profile)


@router.post("/me/addresses/{customer_address_id}/default", response_model=CustomerProfileRead)
async def set_default_customer_address(
    customer_address_id: int,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    customer_address = await _owned_customer_address(session, profile, customer_address_id)
    assert profile.id is not None

    await _clear_default_addresses(session, profile.id)
    customer_address.is_default = True
    session.add(customer_address)
    await session.commit()
    await session.refresh(profile)
    return await _profile_response(session, current_user, profile)


@router.get("/me/credit")
async def get_my_credit(
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
):  # type: ignore[no-untyped-def]
    """Credit accounts this customer holds across stores (limit / outstanding /
    available + status), for the account 'My Credit' view."""
    from app.models.credit import CreditAccount
    from app.models.store import Store
    from app.schemas.credit import CustomerCreditAccountRead

    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    rows = (
        await session.exec(
            select(CreditAccount, Store.name)
            .join(Store, Store.seller_profile_id == CreditAccount.seller_profile_id)
            .where(CreditAccount.customer_profile_id == profile.id)
            .order_by(CreditAccount.created_at.desc())
        )
    ).all()
    return [
        CustomerCreditAccountRead(
            seller_profile_id=acct.seller_profile_id,
            store_name=store_name,
            credit_limit=acct.credit_limit,
            outstanding_balance=acct.outstanding_balance,
            available=round(acct.credit_limit - acct.outstanding_balance, 2),
            status=acct.status.value,
        )
        for acct, store_name in rows
    ]


@router.get("/me/credit/eligibility")
async def get_my_credit_eligibility(
    store_id: int,
    total: float = 0.0,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
):  # type: ignore[no-untyped-def]
    """Display-only credit standing at a store for the checkout UI (non-locking)."""
    from app.schemas.credit import CreditEligibilityRead
    from app.services import credit as credit_svc

    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    data = await credit_svc.credit_eligibility(
        session, customer_profile_id=profile.id, store_id=store_id, cart_total=total
    )
    return CreditEligibilityRead(**data)
