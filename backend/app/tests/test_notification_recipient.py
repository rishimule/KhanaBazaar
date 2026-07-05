# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import Notification, NotificationType


@pytest.mark.asyncio
async def test_seller_notification_persists(session: AsyncSession, approved_seller_with_store) -> None:
    n = Notification(
        seller_profile_id=approved_seller_with_store.profile.id,
        type=NotificationType.FeeActivated,
        title="Activated", body="Your subscription is active.", status_value="active",
    )
    session.add(n)
    await session.commit()
    await session.refresh(n)
    assert n.id is not None
    assert n.customer_profile_id is None
    assert n.seller_profile_id == approved_seller_with_store.profile.id


@pytest.mark.asyncio
async def test_notification_requires_exactly_one_recipient(session: AsyncSession) -> None:
    # Neither recipient set → CHECK violation.
    session.add(Notification(type=NotificationType.FeeExpiring, title="x", body="y", status_value="z"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_notification_rejects_both_recipients(
    session: AsyncSession, approved_seller_with_store
) -> None:
    session.add(Notification(
        customer_profile_id=1, seller_profile_id=approved_seller_with_store.profile.id,
        type=NotificationType.FeeSuspended, title="x", body="y", status_value="z",
    ))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()
