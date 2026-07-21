# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pay-Per-Transaction fee deduction (checkout) + refund (cancel). Operates
inside the caller's atomic transaction; the caller commits."""
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Order
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeEvent,
    FeeEventType,
    FeeModel,
)
from app.services.fee_lifecycle import FeeError, _evaluate_ppt_status, _ppt_config


async def charge_platform_txn_fee(session: AsyncSession, order: Order) -> None:
    """Deduct the flat PPT fee for this order's (store, service). Row-locks the
    arrangement to serialise concurrent orders. No-op unless the arrangement is
    PPT in {Active, Grace}. Part of the caller's transaction."""
    arr = (
        await session.exec(
            select(FeeArrangement)
            .where(
                FeeArrangement.store_id == order.store_id,
                FeeArrangement.service_id == order.service_id,
                FeeArrangement.model == FeeModel.PayPerTransaction,
            )
            .with_for_update()
        )
    ).first()
    if arr is None or arr.status not in (
        ArrangementStatus.Active, ArrangementStatus.Grace
    ):
        return
    try:
        fee, _min_dep, _low = await _ppt_config(session, arr.service_id)
    except FeeError:
        return
    if fee <= 0:
        return
    arr.balance = round(arr.balance - fee, 2)
    session.add(arr)
    session.add(
        FeeEvent(
            arrangement_id=arr.id, event_type=FeeEventType.BalanceDeducted,
            amount_delta=-fee, order_id=order.id, actor="system", note="order fee",
        )
    )
    await session.flush()
    await _evaluate_ppt_status(session, arr)


async def refund_platform_txn_fee(session: AsyncSession, order: Order) -> None:
    """Credit back a previously-charged PPT fee when an order is cancelled.
    Idempotent (guarded by the absence of a prior BalanceRefunded for this
    order). Part of the caller's transaction."""
    deducted = (
        await session.exec(
            select(FeeEvent).where(
                FeeEvent.order_id == order.id,
                FeeEvent.event_type == FeeEventType.BalanceDeducted,
            )
        )
    ).first()
    if deducted is None:
        return
    already = (
        await session.exec(
            select(FeeEvent.id).where(
                FeeEvent.order_id == order.id,
                FeeEvent.event_type == FeeEventType.BalanceRefunded,
            )
        )
    ).first()
    if already is not None:
        return
    amount = abs(deducted.amount_delta or 0.0)
    arr = (
        await session.exec(
            select(FeeArrangement)
            .where(FeeArrangement.id == deducted.arrangement_id)
            .with_for_update()
        )
    ).first()
    if arr is None:
        return
    arr.balance = round(arr.balance + amount, 2)
    session.add(arr)
    session.add(
        FeeEvent(
            arrangement_id=arr.id, event_type=FeeEventType.BalanceRefunded,
            amount_delta=amount, order_id=order.id, actor="system",
            note="order cancelled",
        )
    )
    await session.flush()
    await _evaluate_ppt_status(session, arr)
