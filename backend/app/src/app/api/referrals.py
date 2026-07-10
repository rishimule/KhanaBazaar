# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.otp import (
    CodeExpired,
    InvalidCode,
    TooManyAttempts,
    consume_otp_key,
    normalize_email,
    verify_otp,
)
from app.core.rate_limit import incr_with_ttl
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_referral_invite_token,  # noqa: F401  (re-exported for tests/consumers)
    decode_referral_invite_token,
    get_current_admin,
    get_current_user,
)
from app.db.session import get_db_session
from app.models.base import User
from app.models.referral import Referral, ReferralStatus, ReferralTargetRole
from app.schemas.pagination import PagedResponse
from app.schemas.referrals import (
    AdminReferralReject,
    ReferralAcceptBody,
    ReferralCreate,
    ReferralInviteDetail,
    ReferralRead,
    ReferralSettingsPatch,
    ReferralSettingsRead,
)
from app.services import referrals as svc
from app.services.consent import get_effective_policy_version, record_acceptance

router = APIRouter()
# Admin queue/approve/reject/settings routes are attached in this same module
# (see below); mounted under `/admin` in api/__init__.py.
admin_router = APIRouter()


@router.post("", response_model=ReferralRead, status_code=status.HTTP_201_CREATED)
async def submit_referral(
    body: ReferralCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> ReferralRead:
    # Per-referrer hourly rate limit to curb spam (spec §5.1).
    count = await incr_with_ttl(redis, f"rl:referral:{current_user.id}", ttl=3600)
    if count > settings.REFERRAL_RATE_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429, detail={"error": "rate_limited"})
    try:
        row = await svc.create_referral(
            session,
            source_user_id=int(current_user.id),  # type: ignore[arg-type]
            source_role=current_user.role,
            payload=body,
        )
    except svc.DuplicateContact as exc:
        raise HTTPException(status_code=409, detail={"error": exc.reason}) from exc
    # If approval is disabled the row is already `approved`; mint the invite now
    # but dispatch comms only AFTER commit (so the worker never reads early).
    invite_token: Optional[str] = None
    if row.status == ReferralStatus.approved:
        invite_token = await svc.issue_invite(session, referral=row)
    await session.commit()
    await session.refresh(row)
    if invite_token is not None:
        from app.worker import dispatch_referral_invite

        dispatch_referral_invite(int(row.id), invite_token)  # type: ignore[arg-type]
    return ReferralRead.model_validate(row)


@router.get("", response_model=PagedResponse[ReferralRead])
async def list_my_referrals(
    status_filter: Optional[ReferralStatus] = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PagedResponse[ReferralRead]:
    rows = await svc.list_referrals_for_user(
        session, user_id=int(current_user.id), status=status_filter  # type: ignore[arg-type]
    )
    items = [ReferralRead.model_validate(r) for r in rows]
    return PagedResponse(items=items, total=len(items), page=1, page_size=len(items) or 1)


# Public activation routes. Declared BEFORE `/{referral_id}` so the static
# `/invite` path is not captured as a numeric id.
@router.get("/invite", response_model=ReferralInviteDetail)
async def get_invite_detail(
    token: str,
    session: AsyncSession = Depends(get_db_session),
) -> ReferralInviteDetail:
    claims = decode_referral_invite_token(token)  # raises 410/400
    row = await session.get(Referral, int(claims["referral_id"]))  # type: ignore[call-overload]
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    expired = bool(
        row.invite_expires_at and row.invite_expires_at < datetime.now(timezone.utc)
    )
    return ReferralInviteDetail(
        invitee_name=row.invitee_name,
        target_role=row.target_role,
        invitee_email=row.invitee_email,
        invitee_phone=row.invitee_phone,
        expired=expired,
        status=row.status,
    )


@router.post("/accept")
async def accept_customer_referral(
    body: ReferralAcceptBody,
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:  # type: ignore[type-arg]
    """Customer-target activation. Verifies email OTP, creates the customer,
    binds the referral to `active`, and returns an access token."""
    claims = decode_referral_invite_token(body.token)
    if claims["target_role"] != "customer":
        raise HTTPException(status_code=400, detail={"error": "not_a_customer_invite"})
    # The token's email is authoritative; body.email is only used for phone-only
    # invites (no email captured) since customer accounts are email-keyed.
    token_email = claims.get("email")
    email = normalize_email(str(token_email or body.email or ""))
    if not email:
        raise HTTPException(status_code=400, detail={"error": "email_required"})

    try:
        await verify_otp(email, body.code, redis)
    except CodeExpired:
        raise HTTPException(status_code=410, detail={"error": "code_expired_or_used"}) from None
    except TooManyAttempts:
        raise HTTPException(status_code=429, detail={"error": "too_many_attempts"}) from None
    except InvalidCode:
        raise HTTPException(status_code=400, detail={"error": "invalid_code"}) from None

    effective = await get_effective_policy_version(session)
    if effective is not None and not body.accept_policies:
        raise HTTPException(status_code=400, detail={"error": "policy_acceptance_required"})

    try:
        user, activated = await svc.activate_customer_referral(
            session,
            referral_id=int(claims["referral_id"]),  # type: ignore[call-overload]
            invitee_email=email,
            full_name=body.full_name,
        )
        assert user.id is not None
        await record_acceptance(session, user.id)
        await session.commit()
    except LookupError:
        raise HTTPException(status_code=404, detail={"error": "not_found"}) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
    except IntegrityError:
        # TOCTOU backstop: the email/phone was claimed between the pre-check and
        # the insert (unique constraint tripped) → clean 409, not a 500.
        await session.rollback()
        raise HTTPException(
            status_code=409, detail={"error": "already_registered"}
        ) from None

    await consume_otp_key(email, redis)
    await session.refresh(user)
    await session.refresh(activated)
    # Build the response BEFORE the best-effort notify (notify commits its own
    # write, expiring session objects like `user`).
    access = create_access_token(user)
    response = {
        "access_token": access,
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "role": user.role.value},
    }
    await svc.notify_referral_event(session, referral=activated, event="activated")
    return response


@router.get("/{referral_id}", response_model=ReferralRead)
async def get_my_referral(
    referral_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReferralRead:
    row = await session.get(Referral, referral_id)
    if row is None or row.source_user_id != int(current_user.id):  # type: ignore[arg-type]
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return ReferralRead.model_validate(row)


# ─── Admin queue (mounted under /admin) ──────────────────────────────────
# `/referrals/settings` is declared before `/referrals/{referral_id}` so
# "settings" is never captured as a numeric id.
@admin_router.get("/referrals", response_model=PagedResponse[ReferralRead])
async def admin_list_referrals(
    status_filter: Optional[ReferralStatus] = Query(default=None, alias="status"),
    target_role: Optional[ReferralTargetRole] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> PagedResponse[ReferralRead]:
    rows, total = await svc.list_referrals_admin(
        session, status=status_filter, target_role=target_role, page=page, page_size=page_size
    )
    return PagedResponse(
        items=[ReferralRead.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@admin_router.get("/referrals/settings", response_model=ReferralSettingsRead)
async def admin_get_referral_settings(
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ReferralSettingsRead:
    # Read-only: return the transient default when no row exists yet rather than
    # writing/committing a row on a GET. The row is created on the first PATCH.
    row = await svc.load_referral_settings(session)
    return ReferralSettingsRead.model_validate(row)


@admin_router.patch("/referrals/settings", response_model=ReferralSettingsRead)
async def admin_patch_referral_settings(
    body: ReferralSettingsPatch,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ReferralSettingsRead:
    row = await svc.get_or_create_referral_settings(session)
    row.require_admin_approval = body.require_admin_approval
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return ReferralSettingsRead.model_validate(row)


@admin_router.get("/referrals/{referral_id}", response_model=ReferralRead)
async def admin_get_referral(
    referral_id: int,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ReferralRead:
    row = await session.get(Referral, referral_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return ReferralRead.model_validate(row)


@admin_router.post("/referrals/{referral_id}/approve", response_model=ReferralRead)
async def admin_approve_referral(
    referral_id: int,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ReferralRead:
    try:
        row, invite_token = await svc.approve_referral(
            session, referral_id=referral_id, admin_user_id=int(admin.id)  # type: ignore[arg-type]
        )
    except LookupError:
        raise HTTPException(status_code=404, detail={"error": "not_found"}) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
    await session.commit()
    await session.refresh(row)
    # Post-commit side effects (welcome comms + referrer notification), both
    # best-effort. Build the response BEFORE notify — notify commits its own
    # write, which expires session objects.
    from app.worker import dispatch_referral_invite

    dispatch_referral_invite(int(row.id), invite_token)  # type: ignore[arg-type]
    result = ReferralRead.model_validate(row)
    await svc.notify_referral_event(session, referral=row, event="approved")
    return result


@admin_router.post("/referrals/{referral_id}/reject", response_model=ReferralRead)
async def admin_reject_referral(
    referral_id: int,
    body: AdminReferralReject,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ReferralRead:
    try:
        row = await svc.reject_referral(
            session,
            referral_id=referral_id,
            admin_user_id=int(admin.id),  # type: ignore[arg-type]
            reason=body.reason,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail={"error": "not_found"}) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
    await session.commit()
    await session.refresh(row)
    result = ReferralRead.model_validate(row)
    await svc.notify_referral_event(session, referral=row, event="rejected")
    return result
