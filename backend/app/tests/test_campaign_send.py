# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User, UserRole
from app.models.notification import Notification, NotificationType
from app.models.notification_campaign import (
    CampaignStatus,
    NotificationAudience,
    NotificationCampaign,
)
from app.models.profile import (
    CustomerProfile,
    SellerProfile,
    VerificationStatus,
)
from app.services.notification_campaigns import send_campaign


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    cu1 = User(email="cs-opted@kb.com", role=UserRole.Customer, is_active=True)
    cu2 = User(email="cs-noopt@kb.com", role=UserRole.Customer, is_active=True)
    su = User(email="cs-seller@kb.com", role=UserRole.Seller, is_active=True)
    admin = User(email="cs-admin@kb.com", role=UserRole.Admin, is_active=True)
    for u in (cu1, cu2, su, admin):
        session.add(u)
    await session.flush()

    opted = CustomerProfile(user_id=cu1.id, first_name="Opt", phone="+919811020001", marketing_opt_in=True)
    noopt = CustomerProfile(user_id=cu2.id, first_name="No", phone="+919811020002", marketing_opt_in=False)
    session.add(opted)
    session.add(noopt)
    await session.flush()

    from app.models.address import Address
    from tests._helpers import make_address
    saddr = Address(**make_address())
    session.add(saddr)
    await session.flush()
    seller = SellerProfile(
        user_id=su.id, first_name="S", phone="+919811020003", business_name="S",
        verification_status=VerificationStatus.Approved, business_address_id=saddr.id,
    )
    session.add(seller)
    await session.commit()
    yield {"admin_id": admin.id, "opted": opted.id, "noopt": noopt.id, "seller": seller.id}


async def _make_campaign(
    session: AsyncSession, seed: dict[str, int], *, audience: str, channels: list[str],
    is_essential: bool = False,
) -> NotificationCampaign:
    camp = NotificationCampaign(
        audience=NotificationAudience(audience), filters={}, channels=channels,
        title="Hello", body="World", is_essential=is_essential,
        created_by_admin_id=seed["admin_id"],
    )
    session.add(camp)
    await session.commit()
    await session.refresh(camp)
    return camp


async def test_send_creates_inapp_for_all_and_sets_sent(
    session: AsyncSession, seed: dict[str, int],
) -> None:
    camp = await _make_campaign(session, seed, audience="both", channels=["in_app"])
    await send_campaign(session, camp.id)
    await session.refresh(camp)
    assert camp.status == CampaignStatus.Sent
    assert camp.recipients_targeted == 3
    assert camp.inapp_created == 3
    rows = (await session.exec(select(Notification).where(Notification.campaign_id == camp.id))).all()
    assert len(rows) == 3
    assert all(r.type == NotificationType.Announcement for r in rows)


async def test_email_respects_opt_in(
    session: AsyncSession, seed: dict[str, int],
) -> None:
    camp = await _make_campaign(session, seed, audience="customers", channels=["in_app", "email"])
    with patch("app.worker.send_campaign_email_async") as m:
        await send_campaign(session, camp.id)
    await session.refresh(camp)
    assert camp.email_enqueued == 1                 # only the opted-in customer
    assert m.delay.call_count == 1


async def test_essential_bypasses_opt_in(
    session: AsyncSession, seed: dict[str, int],
) -> None:
    camp = await _make_campaign(
        session, seed, audience="customers", channels=["in_app", "email"], is_essential=True
    )
    with patch("app.worker.send_campaign_email_async") as m:
        await send_campaign(session, camp.id)
    await session.refresh(camp)
    assert camp.email_enqueued == 2                 # both customers (both have email)
    assert m.delay.call_count == 2


async def test_resend_non_draft_guarded(
    session: AsyncSession, seed: dict[str, int],
) -> None:
    camp = await _make_campaign(session, seed, audience="both", channels=["in_app"])
    await send_campaign(session, camp.id)
    with pytest.raises(HTTPException) as exc:
        await send_campaign(session, camp.id)
    assert exc.value.status_code == 409
