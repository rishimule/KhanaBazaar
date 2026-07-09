# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select

from app.models.base import User, UserRole
from app.models.notification import Notification, NotificationType
from app.models.profile import CustomerProfile
from app.models.referral import Referral, ReferralStatus, ReferralTargetRole
from app.services import referrals as svc


def _approved_referral(**over) -> Referral:
    base = dict(
        source_user_id=1,
        source_role=UserRole.Customer,
        target_role=ReferralTargetRole.customer,
        invitee_name="Asha",
        invitee_email="asha@example.com",
        location_state="Maharashtra",
        location_area="Pune",
        status=ReferralStatus.approved,
    )
    base.update(over)
    return Referral(**base)


@pytest.mark.asyncio
async def test_issue_invite_sets_expiry_and_token(session):
    r = _approved_referral()
    session.add(r)
    await session.flush()
    token = await svc.issue_invite_and_dispatch(session, referral=r)
    await session.commit()
    await session.refresh(r)
    assert r.invite_expires_at is not None
    assert isinstance(token, str) and token


@pytest.mark.asyncio
async def test_record_referrer_notification_customer(session):
    user = User(email="ref@x.test", role=UserRole.Customer)
    session.add(user)
    await session.flush()
    prof = CustomerProfile(user_id=user.id, first_name="Ref")
    session.add(prof)
    await session.flush()
    r = _approved_referral(source_user_id=user.id)
    session.add(r)
    await session.flush()
    await svc.record_referral_notification(session, referral=r, event="approved")
    await session.commit()
    notif = (
        await session.exec(
            select(Notification).where(Notification.customer_profile_id == prof.id)
        )
    ).first()
    assert notif is not None
    assert notif.type == NotificationType.Referral
    assert notif.status_value == "approved"
