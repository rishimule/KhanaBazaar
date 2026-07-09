# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Referral onboarding service.

The referral row is its own audit record; there is no separate audit table
(admin_action_log is seller-scoped and does not fit customer-target referrals).
Callers own the transaction — service functions flush, never commit.
"""
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User, UserRole
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
        await session.exec(select(ReferralSettings).order_by(ReferralSettings.id).limit(1))
    ).first()
    return row or ReferralSettings()


async def get_or_create_referral_settings(session: AsyncSession) -> ReferralSettings:
    row = (
        await session.exec(select(ReferralSettings).order_by(ReferralSettings.id).limit(1))
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
