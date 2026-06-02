# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""DB operations for customer notifications + web-push subscriptions."""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import Notification, NotificationType, PushSubscription

_LIST_LIMIT = 50


async def record_order_status_notification(
    session: AsyncSession,
    *,
    customer_profile_id: int,
    order_id: Optional[int],
    status: str,
    title: str,
    body: str,
) -> Notification:
    """Insert (and commit) one order-status notification row."""
    notif = Notification(
        customer_profile_id=customer_profile_id,
        order_id=order_id,
        type=NotificationType.OrderStatus,
        title=title,
        body=body,
        status_value=status,
    )
    session.add(notif)
    await session.commit()
    await session.refresh(notif)
    return notif


async def record_delivery_otp_notification(
    session: AsyncSession,
    *,
    customer_profile_id: int,
    order_id: Optional[int],
    code: str,
) -> Notification:
    """Insert (and commit) one in-app delivery-OTP notification carrying the code."""
    notif = Notification(
        customer_profile_id=customer_profile_id,
        order_id=order_id,
        type=NotificationType.DeliveryOtp,
        title=f"Delivery code for order #{order_id}",
        body=f"Share code {code} with your delivery partner to receive your order.",
        status_value="dispatched",
    )
    session.add(notif)
    await session.commit()
    await session.refresh(notif)
    return notif


async def list_notifications(
    session: AsyncSession, *, customer_profile_id: int
) -> tuple[list[Notification], int]:
    """Return (newest-first notifications, unread_count) for one customer."""
    rows = (
        await session.exec(
            select(Notification)
            .where(Notification.customer_profile_id == customer_profile_id)
            .order_by(col(Notification.created_at).desc())
            .limit(_LIST_LIMIT)
        )
    ).all()
    unread = (
        await session.exec(
            select(func.count())
            .select_from(Notification)
            .where(Notification.customer_profile_id == customer_profile_id)
            .where(Notification.read == False)  # noqa: E712
        )
    ).one()
    return list(rows), int(unread)


async def mark_notification_read(
    session: AsyncSession, *, customer_profile_id: int, notification_id: int
) -> bool:
    """Mark one notification read. Returns False if not found or not owned."""
    notif = (
        await session.exec(
            select(Notification).where(Notification.id == notification_id)
        )
    ).first()
    if notif is None or notif.customer_profile_id != customer_profile_id:
        return False
    if not notif.read:
        notif.read = True
        session.add(notif)
        await session.commit()
    return True


async def mark_all_read(session: AsyncSession, *, customer_profile_id: int) -> int:
    """Mark all of a customer's notifications read. Returns count flipped."""
    rows = (
        await session.exec(
            select(Notification)
            .where(Notification.customer_profile_id == customer_profile_id)
            .where(Notification.read == False)  # noqa: E712
        )
    ).all()
    for notif in rows:
        notif.read = True
        session.add(notif)
    if rows:
        await session.commit()
    return len(rows)


async def upsert_push_subscription(
    session: AsyncSession,
    *,
    customer_profile_id: int,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: Optional[str] = None,
) -> PushSubscription:
    """Create or refresh a push subscription, keyed by unique endpoint.

    Re-binds the endpoint to the current customer (covers the shared-device
    case where a previous user's stale row lingers) and bumps last_seen_at.
    """
    existing = (
        await session.exec(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
    ).first()
    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.customer_profile_id = customer_profile_id
        existing.p256dh = p256dh
        existing.auth = auth
        existing.user_agent = user_agent
        existing.last_seen_at = now
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing
    sub = PushSubscription(
        customer_profile_id=customer_profile_id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        user_agent=user_agent,
        last_seen_at=now,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


async def delete_push_subscription(
    session: AsyncSession, *, customer_profile_id: int, endpoint: str
) -> bool:
    """Delete a subscription by endpoint, scoped to the caller. Idempotent."""
    sub = (
        await session.exec(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
    ).first()
    if sub is None or sub.customer_profile_id != customer_profile_id:
        return False
    await session.delete(sub)
    await session.commit()
    return True
