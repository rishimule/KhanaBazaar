# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select

from app.models.base import UserRole
from app.models.referral import (
    Referral,
    ReferralSettings,
    ReferralStatus,
    ReferralTargetRole,
)


@pytest.mark.asyncio
async def test_referral_row_roundtrips(session):
    row = Referral(
        source_user_id=42,
        source_role=UserRole.Customer,
        target_role=ReferralTargetRole.customer,
        invitee_name="Asha Rao",
        invitee_email="asha@example.com",
        location_state="Maharashtra",
        location_area="Kothrud, Pune",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.id is not None
    assert row.status == ReferralStatus.pending_review
    fetched = (await session.exec(select(Referral).where(Referral.id == row.id))).one()
    assert fetched.invitee_email == "asha@example.com"
    assert fetched.invitee_phone is None


@pytest.mark.asyncio
async def test_referral_settings_defaults(session):
    row = ReferralSettings()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.require_admin_approval is True


def test_notification_type_has_referral():
    from app.models.notification import NotificationType

    assert NotificationType.Referral.value == "referral"
