# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.notification import Notification, NotificationType
from app.models.profile import SellerProfile, VerificationStatus
from app.services.notifications import record_seller_notification
from tests._helpers import make_address


def test_seller_new_order_member_exists() -> None:
    assert NotificationType.SellerNewOrder.value == "seller_new_order"


@pytest.mark.asyncio
async def test_record_seller_notification_persists_order_id(
    session: AsyncSession,
) -> None:
    user = User(id=9101, email="snoa-seller@kb.com", role=UserRole.Seller, is_active=True)
    session.add(user)
    biz_addr = Address(**make_address(pincode="560077"))
    session.add(biz_addr)
    await session.flush()
    profile = SellerProfile(
        user_id=user.id,
        first_name="Snoa",
        business_name="Test Store",
        phone="+919876500011",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz_addr.id,
    )
    session.add(profile)
    await session.flush()

    await record_seller_notification(
        session,
        seller_profile_id=profile.id,
        type=NotificationType.SellerNewOrder,
        title="New order #1",
        body="1 item.",
        status_value="new_order",
        order_id=None,
    )
    await session.commit()

    row = (
        await session.exec(
            select(Notification).where(Notification.seller_profile_id == profile.id)
        )
    ).one()
    assert row.type == NotificationType.SellerNewOrder
    assert row.status_value == "new_order"
    assert row.order_id is None
