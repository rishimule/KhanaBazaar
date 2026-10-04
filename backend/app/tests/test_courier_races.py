# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Two-session races (spec §16). Every courier action takes the order row lock
first, so concurrent requests run one after the other and the second one acts
on the first one's result — never on the state it read before waiting."""
import asyncio

import pytest
from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Order, OrderStatus, Payment, PaymentStatus
from app.models.courier import CourierQuote
from app.services import courier as courier_svc
from app.services.courier_rules import lock_order, refund_owed
from app.services.orders import cancel_order, transition_order_status
from tests._courier_helpers import (
    CUSTOMER,
    SELLER,
    accept_quote,
    claim_payment,
    order_at_dispatched,
    place_courier_order,
    seed_courier_world,
    send_quote,
)
from tests.conftest import test_engine


async def _still_waiting(task: "asyncio.Task[object]") -> bool:
    """True if `task` is still blocked a moment later (on the row lock)."""
    await asyncio.sleep(0.3)
    return not task.done()


async def test_accept_waits_for_a_revision_in_flight_and_sees_it(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    v1 = (await send_quote(order["id"])).json()["courier"]["quotes"][0]
    async with AsyncSession(test_engine) as seller_tx, AsyncSession(test_engine) as customer_tx:
        await lock_order(seller_tx, order["id"])  # the revision holds the row
        target = await customer_tx.get(Order, order["id"])
        assert target is not None
        accept = asyncio.create_task(
            courier_svc.accept_quote(customer_tx, target, CUSTOMER, quote_id=v1["id"])
        )
        assert await _still_waiting(accept)
        seller_tx.add(CourierQuote(
            order_id=order["id"], version=2, courier_fee=150.0, eta_min_days=3,
            eta_max_days=5, created_by_user_id=SELLER.id,
        ))
        await seller_tx.commit()
        with pytest.raises(HTTPException) as exc:
            await accept
    detail: object = exc.value.detail
    assert exc.value.status_code == 409 and detail == {"code": "quote_superseded"}
    fresh = await session.get(Order, order["id"])
    assert fresh is not None
    await session.refresh(fresh)
    assert fresh.status is OrderStatus.Quoted and fresh.delivery_fee == 0


async def test_cancel_and_confirm_racing_end_with_a_refund_owed(session: AsyncSession) -> None:
    """Whichever wins, the money the customer says they sent is owed back:
    confirm-then-cancel leaves Paid on a cancelled order, and cancel-first
    (answering "yes, it arrived") does the same and makes confirm a 409."""
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    quote = (await send_quote(order["id"])).json()["courier"]["quotes"][0]
    assert (await accept_quote(order["id"], quote["id"])).status_code == 200
    assert (await claim_payment(order["id"], "upi")).status_code == 200

    async with (
        AsyncSession(test_engine) as gate,
        AsyncSession(test_engine) as confirm_tx,
        AsyncSession(test_engine) as cancel_tx,
    ):
        await lock_order(gate, order["id"])  # line both requests up behind one lock
        for_confirm = await confirm_tx.get(Order, order["id"])
        for_cancel = await cancel_tx.get(Order, order["id"])
        assert for_confirm is not None and for_cancel is not None
        confirm = asyncio.create_task(courier_svc.confirm_payment(confirm_tx, for_confirm, SELLER))
        cancel = asyncio.create_task(cancel_order(
            cancel_tx, for_cancel, SELLER, reason="Out of stock after all", payment_received=True,
        ))
        assert await _still_waiting(confirm) and not cancel.done()
        await gate.rollback()
        results = await asyncio.gather(confirm, cancel, return_exceptions=True)

    failures = [r for r in results if isinstance(r, Exception)]
    assert len(failures) <= 1, failures
    if failures:  # cancel won; confirm then found a cancelled order
        assert isinstance(failures[0], HTTPException) and failures[0].status_code == 409
    fresh = await session.get(Order, order["id"])
    payment = (await session.exec(select(Payment).where(Payment.order_id == order["id"]))).one()
    assert fresh is not None
    await session.refresh(fresh)
    await session.refresh(payment)
    assert fresh.status is OrderStatus.Cancelled
    assert payment.status is PaymentStatus.Paid
    assert refund_owed(fresh.status, payment.status, payment.amount)


async def test_seller_and_customer_marking_delivered_together(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    async with AsyncSession(test_engine) as seller_tx, AsyncSession(test_engine) as customer_tx:
        for_seller = await seller_tx.get(Order, order["id"])
        for_customer = await customer_tx.get(Order, order["id"])
        assert for_seller is not None and for_customer is not None
        results = await asyncio.gather(
            transition_order_status(seller_tx, for_seller, "delivered", SELLER),
            courier_svc.mark_received(customer_tx, for_customer, CUSTOMER),
            return_exceptions=True,
        )
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(failures) == 1, results
    assert isinstance(failures[0], HTTPException)
    loser: object = failures[0].detail
    assert failures[0].status_code == 409 and loser == {"code": "already_delivered"}
    fresh = await session.get(Order, order["id"])
    assert fresh is not None
    await session.refresh(fresh)
    assert fresh.status is OrderStatus.Delivered
