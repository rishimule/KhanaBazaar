# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select

from app.models.commerce import Delivery, Payment, PaymentMethod, PaymentStatus
from app.models.credit import CreditAccount, CreditEntryType, CreditLedgerEntry
from app.services.checkout import place_order_for_sub_basket
from app.services.orders import cancel_order, transition_order_status
from tests.test_credit_checkout import _seed


async def _deliver_as_seller(session, order, seller_user):
    await transition_order_status(session, order, "packed", seller_user)
    await transition_order_status(session, order, "dispatched", seller_user)
    delivery = (await session.exec(select(Delivery).where(Delivery.order_id == order.id))).one()
    otp = delivery.delivery_otp
    await transition_order_status(session, order, "delivered", seller_user, otp=otp)


@pytest.mark.asyncio
async def test_delivered_credit_order_stays_unpaid(session):
    s = await _seed(session, credit_limit=2000.0)
    order = await place_order_for_sub_basket(
        session, s["user"], customer_address_id=s["address_id"], store_id=s["store_id"], service_id=s["service_id"], payment_method=PaymentMethod.Credit
    )
    await _deliver_as_seller(session, order, s["seller_user"])
    payment = (await session.exec(select(Payment).where(Payment.order_id == order.id))).one()
    assert payment.method == PaymentMethod.Credit
    assert payment.status == PaymentStatus.Pending  # NOT flipped to Paid


@pytest.mark.asyncio
async def test_delivered_upi_order_is_paid(session):
    s = await _seed(session, make_account=False)  # no credit; pay upi
    order = await place_order_for_sub_basket(
        session, s["user"], customer_address_id=s["address_id"], store_id=s["store_id"], service_id=s["service_id"], payment_method=PaymentMethod.Upi
    )
    await _deliver_as_seller(session, order, s["seller_user"])
    payment = (await session.exec(select(Payment).where(Payment.order_id == order.id))).one()
    assert payment.status == PaymentStatus.Paid


@pytest.mark.asyncio
async def test_cancel_credit_order_reverses_charge(session):
    s = await _seed(session, credit_limit=2000.0)
    order = await place_order_for_sub_basket(
        session, s["user"], customer_address_id=s["address_id"], store_id=s["store_id"], service_id=s["service_id"], payment_method=PaymentMethod.Credit
    )
    acct = (await session.exec(select(CreditAccount).where(
        CreditAccount.seller_profile_id == s["seller_profile_id"]))).one()
    assert acct.outstanding_balance == 100.0

    await cancel_order(session, order, s["user"])  # customer cancels their pending order

    await session.refresh(acct)
    assert acct.outstanding_balance == 0.0
    reversal = (await session.exec(select(CreditLedgerEntry).where(
        CreditLedgerEntry.entry_type == CreditEntryType.reversal))).one()
    assert reversal.order_id == order.id
    assert reversal.amount == 100.0
