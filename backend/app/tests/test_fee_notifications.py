# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import NotificationType
from app.services.fee_notifications import notify_seller_fee_event
from app.services.notifications import list_notifications


@pytest.mark.asyncio
async def test_notify_records_seller_notification(
    session: AsyncSession, approved_seller_with_store
) -> None:
    await notify_seller_fee_event(
        session, store_id=approved_seller_with_store.store.id,
        type=NotificationType.FeeActivated, valid_until=date(2026, 10, 1),
    )
    await session.commit()
    items, unread = await list_notifications(
        session, seller_profile_id=approved_seller_with_store.profile.id
    )
    assert unread == 1
    assert items[0].type == NotificationType.FeeActivated
    assert "2026-10-01" in items[0].body  # valid_until surfaced in copy


@pytest.mark.asyncio
async def test_notify_noop_when_store_missing(session: AsyncSession) -> None:
    # Unresolvable store → silent no-op, no exception.
    await notify_seller_fee_event(
        session, store_id=999999, type=NotificationType.FeeSuspended
    )
    await session.commit()  # nothing recorded, no error
