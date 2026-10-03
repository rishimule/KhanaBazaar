# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Courier-only customer and seller messages (spec §11.1).

Generic status changes (placed, packed, shipped, delivered, cancelled) keep
flowing through api.orders.record_and_dispatch_notification; this module
carries the events only courier orders have. Both functions are best-effort —
they never raise into the request path — and refresh the caller's `order`
before returning, because their commit expires it.
"""
import logging

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Order
from app.models.notification import Notification, NotificationType
from app.services.courier_copy import (
    CUSTOMER_EVENTS,
    SELLER_EVENTS,
    load_courier_vars,
    render_customer,
    render_seller,
)
from app.services.notification_push import dispatch_notification_push
from app.services.notifications import (
    record_order_status_notification,
    record_seller_notification,
)
from app.services.order_emails import dispatch_courier_email
from app.services.order_whatsapp import dispatch_courier_whatsapp

logger = logging.getLogger(__name__)


async def _refresh(session: AsyncSession, order: Order) -> None:
    try:
        await session.refresh(order)
    except Exception:
        logger.exception("Refresh after courier notification failed")


async def notify_customer(session: AsyncSession, order: Order, event: str) -> None:
    """In-app row + push for the customer, then email/WhatsApp per CUSTOMER_EVENTS."""
    order_id = order.id
    try:
        assert order_id is not None
        v = await load_courier_vars(session, order_id)
        if v is None or not v.customer_active:
            return
        message = render_customer(event, v)
        notif = await record_order_status_notification(
            session,
            customer_profile_id=v.customer_profile_id,
            order_id=order_id,
            status=f"courier_{event}",
            title=message.title,
            body=message.body,
        )
        if notif.id is not None:
            dispatch_notification_push(notif.id)
        channels = CUSTOMER_EVENTS[event]
        if channels.email:
            dispatch_courier_email(order_id, event, "customer")
        if channels.whatsapp:
            dispatch_courier_whatsapp(order_id, event)
    except Exception:
        try:
            await session.rollback()
        except Exception:
            logger.exception("Rollback after courier customer notification also failed")
        logger.exception("Courier customer notification %s failed for order_id=%s", event, order_id)
    finally:
        await _refresh(session, order)


async def notify_seller(
    session: AsyncSession, order: Order, event: str, *, once: bool = False
) -> None:
    """In-app row for the seller, then email per SELLER_EVENTS. `once` skips
    the event if this order already produced it (e.g. payee_missing)."""
    order_id = order.id
    try:
        assert order_id is not None
        v = await load_courier_vars(session, order_id)
        if v is None or v.seller_profile_id is None or not v.seller_active:
            return
        status_value = f"courier_{event}"
        if once:
            seen = (
                await session.exec(
                    select(Notification.id).where(
                        Notification.seller_profile_id == v.seller_profile_id,
                        Notification.order_id == order_id,
                        Notification.status_value == status_value,
                    )
                )
            ).first()
            if seen is not None:
                return
        message = render_seller(event, v)
        await record_seller_notification(
            session,
            seller_profile_id=v.seller_profile_id,
            type=NotificationType.SellerOrderUpdate,
            title=message.title,
            body=message.body,
            status_value=status_value,
            order_id=order_id,
        )
        await session.commit()
        if SELLER_EVENTS[event].email:
            dispatch_courier_email(order_id, event, "seller")
    except Exception:
        try:
            await session.rollback()
        except Exception:
            logger.exception("Rollback after courier seller notification also failed")
        logger.exception("Courier seller notification %s failed for order_id=%s", event, order_id)
    finally:
        await _refresh(session, order)
