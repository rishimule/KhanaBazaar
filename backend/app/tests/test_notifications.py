# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User, UserRole
from app.models.profile import CustomerProfile


async def _make_customer(session: AsyncSession) -> int:
    user = User(email="notif-cust@kb.com", role=UserRole.Customer, is_active=True)
    session.add(user)
    await session.flush()
    profile = CustomerProfile(user_id=user.id, first_name="Nina")
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile.id


@pytest.mark.asyncio
async def test_record_and_list_notifications(session: AsyncSession) -> None:
    from app.services.notifications import (
        list_notifications,
        record_order_status_notification,
    )

    cpid = await _make_customer(session)
    notif = await record_order_status_notification(
        session, customer_profile_id=cpid, order_id=None, status="dispatched",
        title="Order #42 dispatched", body="Your order is on its way.",
    )
    assert notif.id is not None
    assert notif.read is False

    items, unread = await list_notifications(session, customer_profile_id=cpid)
    assert len(items) == 1
    assert unread == 1
    assert items[0].status_value == "dispatched"


@pytest.mark.asyncio
async def test_mark_read_and_mark_all(session: AsyncSession) -> None:
    from app.services.notifications import (
        list_notifications,
        mark_all_read,
        mark_notification_read,
        record_order_status_notification,
    )

    cpid = await _make_customer(session)
    n1 = await record_order_status_notification(
        session, customer_profile_id=cpid, order_id=None, status="packed",
        title="t", body="b",
    )
    n1_id = n1.id
    assert n1_id is not None
    await record_order_status_notification(
        session, customer_profile_id=cpid, order_id=None, status="delivered",
        title="t", body="b",
    )

    ok = await mark_notification_read(session, customer_profile_id=cpid, notification_id=n1_id)
    assert ok is True
    _, unread = await list_notifications(session, customer_profile_id=cpid)
    assert unread == 1

    await mark_all_read(session, customer_profile_id=cpid)
    _, unread = await list_notifications(session, customer_profile_id=cpid)
    assert unread == 0


@pytest.mark.asyncio
async def test_mark_read_rejects_other_customer(session: AsyncSession) -> None:
    from app.services.notifications import (
        mark_notification_read,
        record_order_status_notification,
    )

    owner = await _make_customer(session)
    notif = await record_order_status_notification(
        session, customer_profile_id=owner, order_id=None, status="packed",
        title="t", body="b",
    )
    assert notif.id is not None
    ok = await mark_notification_read(
        session, customer_profile_id=owner + 999, notification_id=notif.id
    )
    assert ok is False


@pytest.mark.asyncio
async def test_upsert_and_delete_subscription(session: AsyncSession) -> None:
    from sqlmodel import select

    from app.models.notification import PushSubscription
    from app.services.notifications import (
        delete_push_subscription,
        upsert_push_subscription,
    )

    cpid = await _make_customer(session)
    await upsert_push_subscription(
        session, customer_profile_id=cpid, endpoint="https://push.example/a",
        p256dh="k1", auth="a1", user_agent="UA1",
    )
    # Upsert with the same endpoint must not create a duplicate row.
    await upsert_push_subscription(
        session, customer_profile_id=cpid, endpoint="https://push.example/a",
        p256dh="k2", auth="a2", user_agent="UA2",
    )
    rows = (
        await session.exec(
            select(PushSubscription).where(PushSubscription.endpoint == "https://push.example/a")
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].p256dh == "k2"  # refreshed in place

    ok = await delete_push_subscription(
        session, customer_profile_id=cpid, endpoint="https://push.example/a"
    )
    assert ok is True
    remaining = (
        await session.exec(select(PushSubscription).where(PushSubscription.customer_profile_id == cpid))
    ).all()
    assert remaining == []
