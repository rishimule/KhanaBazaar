# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Referral onboarding service.

The referral row is its own audit record; there is no separate audit table
(admin_action_log is seller-scoped and does not fit customer-target referrals).
Callers own the transaction — service functions flush, never commit.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.security import create_referral_invite_token
from app.models.base import User, UserRole
from app.models.notification import Notification, NotificationType
from app.models.profile import AdminProfile, CustomerProfile, SellerProfile
from app.models.referral import (
    Referral,
    ReferralSettings,
    ReferralStatus,
    ReferralTargetRole,
)
from app.schemas.referrals import ReferralCreate

_OPEN = (ReferralStatus.pending_review, ReferralStatus.approved)


class DuplicateContact(Exception):
    """Raised when a referral contact collides with an existing user/profile
    (``already_registered``) or an open referral (``already_invited``)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


async def load_referral_settings(session: AsyncSession) -> ReferralSettings:
    """The single settings row, or a transient default (unsaved) if none yet."""
    row = (
        await session.exec(select(ReferralSettings).order_by(ReferralSettings.id).limit(1))  # type: ignore[arg-type]
    ).first()
    return row or ReferralSettings()


async def get_or_create_referral_settings(session: AsyncSession) -> ReferralSettings:
    row = (
        await session.exec(select(ReferralSettings).order_by(ReferralSettings.id).limit(1))  # type: ignore[arg-type]
    ).first()
    if row is None:
        row = ReferralSettings()
        session.add(row)
        await session.flush()
    return row


async def assert_contact_available(
    session: AsyncSession, *, email: Optional[str], phone: Optional[str]
) -> None:
    """Global dedupe: reject if the contact belongs to an existing user/profile
    (already_registered) or to an OPEN referral (already_invited)."""
    if email:
        if (await session.exec(select(User).where(User.email == email))).first():
            raise DuplicateContact("already_registered")
    if phone:
        for model in (CustomerProfile, SellerProfile, AdminProfile):
            if (await session.exec(select(model).where(model.phone == phone))).first():
                raise DuplicateContact("already_registered")
    open_conds = []
    if email:
        open_conds.append(Referral.invitee_email == email)
    if phone:
        open_conds.append(Referral.invitee_phone == phone)
    for cond in open_conds:
        existing = (
            await session.exec(
                select(Referral).where(cond).where(Referral.status.in_(_OPEN))  # type: ignore[attr-defined]
            )
        ).first()
        if existing:
            raise DuplicateContact("already_invited")


async def create_referral(
    session: AsyncSession,
    *,
    source_user_id: int,
    source_role: UserRole,
    payload: ReferralCreate,
) -> Referral:
    await assert_contact_available(
        session, email=payload.invitee_email, phone=payload.invitee_phone
    )
    settings_row = await load_referral_settings(session)
    status = (
        ReferralStatus.pending_review
        if settings_row.require_admin_approval
        else ReferralStatus.approved
    )
    row = Referral(
        source_user_id=source_user_id,
        source_role=source_role,
        target_role=payload.target_role,
        invitee_name=payload.invitee_name,
        invitee_phone=payload.invitee_phone,
        invitee_email=payload.invitee_email,
        location_state=payload.location_state,
        location_area=payload.location_area,
        status=status,
    )
    session.add(row)
    await session.flush()
    return row


async def list_referrals_for_user(
    session: AsyncSession, *, user_id: int, status: Optional[ReferralStatus]
) -> list[Referral]:
    stmt = select(Referral).where(Referral.source_user_id == user_id)
    if status is not None:
        stmt = stmt.where(Referral.status == status)
    stmt = stmt.order_by(Referral.created_at.desc())  # type: ignore[attr-defined]
    return list((await session.exec(stmt)).all())


async def _resolve_referrer_profile_id(
    session: AsyncSession, *, user_id: int, role: UserRole
) -> tuple[Optional[int], Optional[int]]:
    """Return (customer_profile_id, seller_profile_id) for the referrer — at
    most one non-None. Admin referrers get no in-app notification."""
    if role == UserRole.Customer:
        pid = (
            await session.exec(
                select(CustomerProfile.id).where(CustomerProfile.user_id == user_id)
            )
        ).first()
        return (pid, None)
    if role == UserRole.Seller:
        pid = (
            await session.exec(
                select(SellerProfile.id).where(SellerProfile.user_id == user_id)
            )
        ).first()
        return (None, pid)
    return (None, None)


_NOTIF_COPY = {
    "approved": ("Referral approved", "Your referral for {name} was approved and invited."),
    "rejected": ("Referral rejected", "Your referral for {name} was not approved."),
    "activated": ("Referral joined", "{name} joined via your referral."),
}


async def record_referral_notification(
    session: AsyncSession, *, referral: Referral, event: str
) -> None:
    """Insert (flush, not commit) an in-app notification for the referrer.
    Best-effort: no-op for admin referrers or referrers without a profile."""
    copy = _NOTIF_COPY.get(event)
    if copy is None:
        return
    cust_id, seller_id = await _resolve_referrer_profile_id(
        session, user_id=referral.source_user_id, role=referral.source_role
    )
    if cust_id is None and seller_id is None:
        return
    title, body_tmpl = copy
    notif = Notification(
        customer_profile_id=cust_id,
        seller_profile_id=seller_id,
        type=NotificationType.Referral,
        title=title,
        body=body_tmpl.format(name=referral.invitee_name),
        status_value=event,
    )
    session.add(notif)
    await session.flush()


async def issue_invite_and_dispatch(session: AsyncSession, *, referral: Referral) -> str:
    """Set the invite expiry, mint the invite token, and enqueue welcome comms.
    Caller commits. Returns the token (useful for tests)."""
    referral.invite_expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.REFERRAL_INVITE_EXPIRY_DAYS
    )
    session.add(referral)
    await session.flush()
    assert referral.id is not None
    token = create_referral_invite_token(
        referral_id=referral.id,
        target_role=referral.target_role.value,
        email=referral.invitee_email,
        phone=referral.invitee_phone,
        expires_days=settings.REFERRAL_INVITE_EXPIRY_DAYS,
    )
    from app.worker import dispatch_referral_invite

    dispatch_referral_invite(referral.id, token)
    return token


async def activate_customer_referral(
    session: AsyncSession,
    *,
    referral_id: int,
    invitee_email: str,
    full_name: Optional[str],
) -> tuple[User, Referral]:
    """Create the customer account + bind the referral to `active`. The caller
    verifies OTP + handles policy acceptance + commits. Raises LookupError
    (not found) / ValueError('expired'|'not_approved'|'already_active'|
    'already_registered')."""
    from app.services.profiles import split_full_name

    row = await session.get(Referral, referral_id)
    if row is None:
        raise LookupError("not_found")
    if row.status == ReferralStatus.active:
        raise ValueError("already_active")
    if row.status != ReferralStatus.approved:
        raise ValueError("not_approved")
    if row.invite_expires_at and row.invite_expires_at < datetime.now(timezone.utc):
        row.status = ReferralStatus.expired
        session.add(row)
        await session.flush()
        raise ValueError("expired")
    # Guard the window between approve and accept.
    if (await session.exec(select(User).where(User.email == invitee_email))).first():
        raise ValueError("already_registered")

    first_name, last_name = split_full_name(full_name or row.invitee_name)
    user = User(email=invitee_email, role=UserRole.Customer)
    session.add(user)
    await session.flush()
    assert user.id is not None
    profile = CustomerProfile(
        user_id=user.id,
        first_name=first_name,
        last_name=last_name,
        phone=row.invitee_phone,
    )
    session.add(profile)
    row.status = ReferralStatus.active
    row.activated_user_id = user.id
    row.activated_at = datetime.now(timezone.utc)
    session.add(row)
    await session.flush()
    await record_referral_notification(session, referral=row, event="activated")
    return user, row


async def bind_seller_referral(
    session: AsyncSession, *, referral_id: int, user_id: int
) -> None:
    """Bind a seller-target referral to the seller account created via the
    signup wizard. Best-effort — never blocks seller signup."""
    row = await session.get(Referral, referral_id)
    if row is None or row.status != ReferralStatus.approved:
        return
    row.status = ReferralStatus.active
    row.activated_user_id = user_id
    row.activated_at = datetime.now(timezone.utc)
    session.add(row)
    await session.flush()
    await record_referral_notification(session, referral=row, event="activated")


async def run_referral_expiry_sweep(session: AsyncSession) -> int:
    """Transition approved referrals whose invite has lapsed to expired.
    Caller commits."""
    now = datetime.now(timezone.utc)
    rows = (
        await session.exec(
            select(Referral)
            .where(Referral.status == ReferralStatus.approved)
            .where(Referral.invite_expires_at.is_not(None))  # type: ignore[union-attr]
            .where(Referral.invite_expires_at < now)  # type: ignore[operator]
        )
    ).all()
    for row in rows:
        row.status = ReferralStatus.expired
        session.add(row)
    await session.flush()
    return len(rows)


async def list_referrals_admin(
    session: AsyncSession,
    *,
    status: Optional[ReferralStatus],
    target_role: Optional[ReferralTargetRole],
    page: int,
    page_size: int,
) -> tuple[list[Referral], int]:
    from sqlalchemy import func

    base = select(Referral)
    if status is not None:
        base = base.where(Referral.status == status)
    if target_role is not None:
        base = base.where(Referral.target_role == target_role)
    total = (
        await session.exec(select(func.count()).select_from(base.subquery()))
    ).one()
    rows = (
        await session.exec(
            base.order_by(Referral.created_at.desc())  # type: ignore[attr-defined]
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return list(rows), int(total)


async def approve_referral(
    session: AsyncSession, *, referral_id: int, admin_user_id: int
) -> Referral:
    """Approve a pending referral: issue the invite + notify the referrer.
    Raises LookupError (not found) / ValueError('not_pending')."""
    row = await session.get(Referral, referral_id)
    if row is None:
        raise LookupError("not_found")
    if row.status != ReferralStatus.pending_review:
        raise ValueError("not_pending")
    row.status = ReferralStatus.approved
    row.reviewed_by_admin_id = admin_user_id
    row.reviewed_at = datetime.now(timezone.utc)
    session.add(row)
    await session.flush()
    await issue_invite_and_dispatch(session, referral=row)
    await record_referral_notification(session, referral=row, event="approved")
    return row


async def reject_referral(
    session: AsyncSession, *, referral_id: int, admin_user_id: int, reason: str
) -> Referral:
    row = await session.get(Referral, referral_id)
    if row is None:
        raise LookupError("not_found")
    if row.status != ReferralStatus.pending_review:
        raise ValueError("not_pending")
    row.status = ReferralStatus.rejected
    row.rejection_reason = reason
    row.reviewed_by_admin_id = admin_user_id
    row.reviewed_at = datetime.now(timezone.utc)
    session.add(row)
    await session.flush()
    await record_referral_notification(session, referral=row, event="rejected")
    return row
