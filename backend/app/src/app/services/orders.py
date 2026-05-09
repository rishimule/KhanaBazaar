# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User, UserRole
from app.models.commerce import (
    Delivery,
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
)
from app.models.profile import CustomerProfile, SellerProfile
from app.models.store import Store
from app.services.inventory import lock_inventory_rows, restock

LEGAL_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.Pending: {OrderStatus.Packed, OrderStatus.Cancelled},
    OrderStatus.Packed: {OrderStatus.Dispatched, OrderStatus.Cancelled},
    OrderStatus.Dispatched: {OrderStatus.Delivered, OrderStatus.Cancelled},
    OrderStatus.Delivered: set(),
    OrderStatus.Cancelled: set(),
}

TARGET_BY_STR: dict[str, OrderStatus] = {
    "packed": OrderStatus.Packed,
    "dispatched": OrderStatus.Dispatched,
    "delivered": OrderStatus.Delivered,
}


async def _seller_owns_store(session: AsyncSession, user: User, store_id: int) -> bool:
    profile_result = await session.exec(
        select(SellerProfile.id).where(SellerProfile.user_id == user.id)
    )
    profile_id = profile_result.first()
    if profile_id is None:
        return False
    store_result = await session.exec(
        select(Store.id).where(Store.id == store_id, Store.seller_profile_id == profile_id)
    )
    return store_result.first() is not None


async def transition_order_status(
    session: AsyncSession, order: Order, target_str: Literal["packed", "dispatched", "delivered"], actor: User,
) -> Order:
    target = TARGET_BY_STR[target_str]
    if target not in LEGAL_TRANSITIONS.get(order.status, set()):
        raise HTTPException(status_code=409, detail={
            "detail": "illegal_transition", "from": order.status.value, "to": target.value,
        })

    # Authorization: seller owns store or admin.
    if actor.role == UserRole.Seller:
        if not await _seller_owns_store(session, actor, order.store_id):
            raise HTTPException(status_code=403, detail="forbidden")
    elif actor.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="forbidden")

    delivery_result = await session.exec(select(Delivery).where(Delivery.order_id == order.id))
    delivery = delivery_result.first()
    if delivery is None:
        raise HTTPException(status_code=500, detail="delivery_missing")

    now = datetime.now(timezone.utc)
    order.status = target
    if target == OrderStatus.Packed:
        delivery.status = DeliveryStatus.Packed
        delivery.packed_at = now
    elif target == OrderStatus.Dispatched:
        delivery.status = DeliveryStatus.Dispatched
        delivery.dispatched_at = now
    elif target == OrderStatus.Delivered:
        delivery.status = DeliveryStatus.Delivered
        delivery.delivered_at = now
        payment_result = await session.exec(select(Payment).where(Payment.order_id == order.id))
        payment = payment_result.first()
        if payment is not None:
            payment.status = PaymentStatus.Paid
            payment.paid_at = now

    await session.commit()
    await session.refresh(order)
    return order


async def _authorize_cancel(session: AsyncSession, actor: User, order: Order) -> None:
    if actor.role == UserRole.Customer:
        if order.status != OrderStatus.Pending:
            raise HTTPException(status_code=403, detail="cancel_not_allowed")
        cust_result = await session.exec(
            select(CustomerProfile.id).where(CustomerProfile.user_id == actor.id)
        )
        if cust_result.first() != order.customer_profile_id:
            raise HTTPException(status_code=403, detail="forbidden")
    elif actor.role == UserRole.Seller:
        if not await _seller_owns_store(session, actor, order.store_id):
            raise HTTPException(status_code=403, detail="forbidden")
    elif actor.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="forbidden")


async def cancel_order(session: AsyncSession, order: Order, actor: User) -> Order:
    if order.status in (OrderStatus.Delivered, OrderStatus.Cancelled):
        raise HTTPException(status_code=409, detail="terminal_status")

    await _authorize_cancel(session, actor, order)

    delivery_result = await session.exec(select(Delivery).where(Delivery.order_id == order.id))
    delivery = delivery_result.first()
    payment_result = await session.exec(select(Payment).where(Payment.order_id == order.id))
    payment = payment_result.first()

    order.status = OrderStatus.Cancelled
    if delivery is not None:
        delivery.status = DeliveryStatus.Cancelled
    # NOTE: dormant today — Delivered is terminal so Paid orders cannot reach
    # cancel. If a future workflow lets admins cancel post-Delivered, audit
    # this branch (real money refund, not just bookkeeping).
    if payment is not None and payment.status == PaymentStatus.Paid:
        payment.status = PaymentStatus.Refunded

    items_result = await session.exec(select(OrderItem).where(OrderItem.order_id == order.id))
    items = list(items_result.all())
    inv_ids = [item.inventory_id for item in items if item.inventory_id is not None]
    locked_inv = await lock_inventory_rows(session, inv_ids)
    inv_by_id = {inv.id: inv for inv in locked_inv}
    for item in items:
        if item.inventory_id is None:
            continue
        inv = inv_by_id.get(item.inventory_id)
        if inv is not None:
            restock(inv, item.quantity)

    await session.commit()
    await session.refresh(order)
    return order
