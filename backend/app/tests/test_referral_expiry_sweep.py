# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone

import pytest

from app.models.base import UserRole
from app.models.referral import Referral, ReferralStatus, ReferralTargetRole
from app.services.referrals import run_referral_expiry_sweep


def _referral(email: str, *, expires_delta_days: int) -> Referral:
    return Referral(
        source_user_id=1,
        source_role=UserRole.Customer,
        target_role=ReferralTargetRole.customer,
        invitee_name="Test",
        invitee_email=email,
        location_state="Maharashtra",
        location_area="Pune",
        status=ReferralStatus.approved,
        invite_expires_at=datetime.now(timezone.utc) + timedelta(days=expires_delta_days),
    )


@pytest.mark.asyncio
async def test_sweep_expires_stale_approved(session):
    stale = _referral("old@example.com", expires_delta_days=-1)
    fresh = _referral("new@example.com", expires_delta_days=1)
    session.add(stale)
    session.add(fresh)
    await session.commit()
    n = await run_referral_expiry_sweep(session)
    await session.commit()
    await session.refresh(stale)
    await session.refresh(fresh)
    assert n == 1
    assert stale.status == ReferralStatus.expired
    assert fresh.status == ReferralStatus.approved
