# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest

from app.models.base import User, UserRole
from app.models.referral import ReferralStatus, ReferralTargetRole
from app.schemas.referrals import ReferralCreate
from app.services import referrals as svc


def _payload(**over):
    base = dict(
        target_role=ReferralTargetRole.customer,
        invitee_name="Asha",
        invitee_email="asha@example.com",
        location_state="Maharashtra",
        location_area="Pune",
    )
    base.update(over)
    return ReferralCreate(**base)


@pytest.mark.asyncio
async def test_create_referral_pending_by_default(session):
    r = await svc.create_referral(
        session, source_user_id=7, source_role=UserRole.Customer, payload=_payload()
    )
    await session.commit()
    assert r.status == ReferralStatus.pending_review
    assert r.source_user_id == 7


@pytest.mark.asyncio
async def test_duplicate_existing_user_blocks(session):
    session.add(User(email="asha@example.com", role=UserRole.Customer))
    await session.commit()
    with pytest.raises(svc.DuplicateContact) as ei:
        await svc.assert_contact_available(session, email="asha@example.com", phone=None)
    assert ei.value.reason == "already_registered"


@pytest.mark.asyncio
async def test_duplicate_open_referral_blocks(session):
    await svc.create_referral(
        session, source_user_id=7, source_role=UserRole.Customer, payload=_payload()
    )
    await session.commit()
    with pytest.raises(svc.DuplicateContact) as ei:
        await svc.assert_contact_available(session, email="asha@example.com", phone=None)
    assert ei.value.reason == "already_invited"


@pytest.mark.asyncio
async def test_auto_approve_when_setting_disabled(session):
    settings_row = await svc.get_or_create_referral_settings(session)
    settings_row.require_admin_approval = False
    session.add(settings_row)
    await session.commit()
    r = await svc.create_referral(
        session, source_user_id=7, source_role=UserRole.Customer,
        payload=_payload(invitee_email="auto@example.com"),
    )
    await session.commit()
    assert r.status == ReferralStatus.approved
