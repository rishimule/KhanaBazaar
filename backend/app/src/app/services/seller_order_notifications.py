# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""In-app 'new order' notification for the seller who owns the store.

Best-effort: never raises into the checkout request path, and rolls back its own
failed write so the shared request session stays usable for the response
serializer (same contract as api.orders.record_and_dispatch_notification).
English-only copy, matching every other seller notification in the repo.
"""
import logging

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import AccountStatus, User
from app.models.commerce import DeliveryMode, Order, OrderItem
from app.models.notification import NotificationType
from app.models.profile import SellerProfile
from app.models.store import Store
from app.services.notifications import record_seller_notification

logger = logging.getLogger(__name__)


async def record_seller_new_order_notification(
    session: AsyncSession, order: Order
) -> None:
    """Record + commit one SellerNewOrder notification. Never raises."""
    # Captured up front: a rollback in the except-branch expires the ORM
    # instance, so touching order.id afterwards would itself raise
    # MissingGreenlet from inside the error handler.
    order_id = order.id
    try:
        row = (
            await session.exec(
                select(SellerProfile.id, User.account_status)
                .join(Store, Store.seller_profile_id == SellerProfile.id)  # type: ignore[arg-type]
                .join(User, User.id == SellerProfile.user_id)  # type: ignore[arg-type]
                .where(Store.id == order.store_id)
            )
        ).first()
        if row is None:
            return
        seller_profile_id, account_status = row
        if account_status != AccountStatus.active:
            return

        item_count = int(
            (
                await session.exec(
                    select(func.count())
                    .select_from(OrderItem)
                    .where(OrderItem.order_id == order.id)
                )
            ).one()
        )
        mode = "Pickup" if order.delivery_mode == DeliveryMode.Pickup else "Delivery"
        parts: list[str] = []
        if item_count:
            parts.append(f"{item_count} item" + ("s" if item_count != 1 else ""))
        parts.append(order.service_name_snapshot)
        parts.append(mode)

        await record_seller_notification(
            session,
            seller_profile_id=seller_profile_id,
            type=NotificationType.SellerNewOrder,
            title=f"New order #{order.id} · ₹{order.total:.2f}",
            body=f"{' · '.join(parts)}. Tap to pack it.",
            status_value="new_order",
            order_id=order.id,
        )
        await session.commit()
        await session.refresh(order)
    except Exception:
        try:
            await session.rollback()
            # The rollback expired `order`; refresh it explicitly so the
            # caller's response serializer doesn't trip MissingGreenlet on the
            # first lazy attribute read.
            await session.refresh(order)
        except Exception:
            logger.exception("Rollback after seller notification failure also failed")
        logger.exception(
            "Failed to record seller new-order notification for order_id=%s", order_id
        )
