# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Return settlement: decide where the returned value goes.

Fixed order (spec §7.2):
  1. Reverse postpaid credit debt, capped at the CURRENT outstanding balance.
     Repayments are not allocated per order, so "how much of this order is
     still owed" is unanswerable — whatever is outstanding is debt to this
     seller, and reducing it is always fair value.
  2. The remainder follows the customer's choice: store credit (closes now) or
     cash/UPI (parks until the customer confirms receipt by OTP).

Flushes; the caller commits and owns the status transition.
"""
from dataclasses import dataclass
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Payment, PaymentMethod
from app.models.returns import (
    ReturnRequest,
    ReturnSettlementChoice,
    ReturnStatus,
    StoreCreditEntryType,
)
from app.services import credit as credit_svc
from app.services import customer_store_credit as store_credit_svc


@dataclass
class SettlementResult:
    credit_reversal_amount: float
    store_credit_amount: float
    payment_amount: float
    next_status: ReturnStatus


async def settle(
    session: AsyncSession, request: ReturnRequest, *, actor_user_id: Optional[int]
) -> SettlementResult:
    """Split `request.total_amount` and record the three components on the row."""
    assert request.id is not None
    remaining = round(request.total_amount, 2)
    reversal = 0.0

    payment = (
        await session.exec(select(Payment).where(Payment.order_id == request.order_id))
    ).first()
    if payment is not None and payment.method == PaymentMethod.Credit:
        account = await credit_svc.lock_credit_account(
            session, request.seller_profile_id, request.customer_profile_id
        )
        if account is not None and account.outstanding_balance > 0:
            reversal = round(min(remaining, account.outstanding_balance), 2)
            if reversal > 0:
                await credit_svc.reverse_credit_charge(
                    session,
                    store_id=request.store_id,
                    customer_profile_id=request.customer_profile_id,
                    order_id=request.order_id,
                    amount=reversal,
                )
                remaining = round(remaining - reversal, 2)

    store_credit_amount = 0.0
    payment_amount = 0.0
    if remaining <= 0:
        # Fully absorbed by the reversal — there is nothing left to hand over,
        # so the return closes even if the customer asked for money back.
        next_status = ReturnStatus.closed
    elif request.settlement_choice == ReturnSettlementChoice.store_credit:
        account_credit = await store_credit_svc.get_or_create_account(
            session,
            seller_profile_id=request.seller_profile_id,
            customer_profile_id=request.customer_profile_id,
        )
        await store_credit_svc.grant(
            session, account_credit, remaining,
            entry_type=StoreCreditEntryType.return_credit,
            return_request_id=request.id,
            note=f"return #{request.id}",
            actor_user_id=actor_user_id,
        )
        store_credit_amount = remaining
        next_status = ReturnStatus.closed
    else:
        payment_amount = remaining
        next_status = ReturnStatus.awaiting_payment_confirmation

    request.credit_reversal_amount = reversal
    request.store_credit_amount = store_credit_amount
    request.payment_amount = payment_amount
    session.add(request)
    await session.flush()

    return SettlementResult(
        credit_reversal_amount=reversal,
        store_credit_amount=store_credit_amount,
        payment_amount=payment_amount,
        next_status=next_status,
    )
