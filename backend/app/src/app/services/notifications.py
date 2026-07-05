# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""DB operations for customer notifications + web-push subscriptions."""
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import Notification, NotificationType, PushSubscription

_LIST_LIMIT = 50


def _recipient_filter(
    customer_profile_id: int | None, seller_profile_id: int | None
) -> tuple[Any, int]:
    """Return the (column, value) to scope a notification query by recipient.

    Exactly one of the two ids must be provided.
    """
    if (customer_profile_id is None) == (seller_profile_id is None):
        raise ValueError("exactly one of customer_profile_id / seller_profile_id required")
    if seller_profile_id is not None:
        return Notification.seller_profile_id, seller_profile_id
    return Notification.customer_profile_id, customer_profile_id


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


async def record_seller_notification(
    session: AsyncSession,
    *,
    seller_profile_id: int,
    type: NotificationType,  # noqa: A002 - matches the model field name
    title: str,
    body: str,
    status_value: str,
) -> Notification:
    """Insert (flush, not commit) one seller notification row."""
    notif = Notification(
        seller_profile_id=seller_profile_id,
        type=type,
        title=title,
        body=body,
        status_value=status_value,
    )
    session.add(notif)
    await session.flush()
    return notif


async def list_notifications(
    session: AsyncSession,
    *,
    customer_profile_id: int | None = None,
    seller_profile_id: int | None = None,
) -> tuple[list[Notification], int]:
    """Return (newest-first notifications, unread_count) for one recipient."""
    col_, val = _recipient_filter(customer_profile_id, seller_profile_id)
    rows = (
        await session.exec(
            select(Notification)
            .where(col_ == val)
            .order_by(col(Notification.created_at).desc())
            .limit(_LIST_LIMIT)
        )
    ).all()
    unread = (
        await session.exec(
            select(func.count())
            .select_from(Notification)
            .where(col_ == val)
            .where(Notification.read == False)  # noqa: E712
        )
    ).one()
    return list(rows), int(unread)


async def mark_notification_read(
    session: AsyncSession,
    *,
    notification_id: int,
    customer_profile_id: int | None = None,
    seller_profile_id: int | None = None,
) -> bool:
    """Mark one notification read. Returns False if not found or not owned."""
    col_, val = _recipient_filter(customer_profile_id, seller_profile_id)
    notif = (
        await session.exec(
            select(Notification).where(Notification.id == notification_id)
        )
    ).first()
    if notif is None or getattr(notif, col_.key) != val:
        return False
    if not notif.read:
        notif.read = True
        session.add(notif)
        await session.commit()
    return True


async def mark_all_read(
    session: AsyncSession,
    *,
    customer_profile_id: int | None = None,
    seller_profile_id: int | None = None,
) -> int:
    """Mark all of a recipient's notifications read. Returns count flipped."""
    col_, val = _recipient_filter(customer_profile_id, seller_profile_id)
    rows = (
        await session.exec(
            select(Notification)
            .where(col_ == val)
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
