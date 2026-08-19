# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Return settlement: decide where the returned value goes.

Two rules, in this order (spec §7.2):

1. **Value comes back in the tender it went out in.** Store credit spent on the
   order returns as store credit — never as cash and never as a debt reversal.
   Without this, a customer who paid 400 of store credit and 100 of cash for a
   500 order could return it for 500 cash and launder seller-scoped credit into
   money, repeatedly. The split is proportional to the return's share of the
   order, so partial returns behave sensibly too.
2. **The cash-funded remainder reverses postpaid debt first**, capped at the
   CURRENT outstanding balance (repayments are not allocated per order, so "how
   much of this order is still owed" is unanswerable), then follows the
   customer's choice: store credit closes immediately, cash parks in
   `awaiting_payment_confirmation`.

Lock order is store credit → credit account, matching `services/checkout.py`.
Acquiring them in the opposite order deadlocks a checkout against a settlement
for the same (seller, customer) pair.

Flushes; the caller commits and owns the status transition.
"""
from dataclasses import dataclass
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Order, Payment, PaymentMethod
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


def split_by_tender(
    return_total: float, *, order_total: float, store_credit_applied: float
) -> tuple[float, float]:
    """Split a return amount into (store-credit-funded, cash-funded).

    Proportional to how the order itself was paid. Returns (0, return_total)
    when the order used no store credit, which is the common case.
    """
    if store_credit_applied <= 0 or order_total <= 0:
        return 0.0, round(return_total, 2)
    credit_share = round(return_total * store_credit_applied / order_total, 2)
    credit_share = min(credit_share, round(return_total, 2))
    return credit_share, round(return_total - credit_share, 2)


async def settle(
    session: AsyncSession, request: ReturnRequest, *, actor_user_id: Optional[int]
) -> SettlementResult:
    """Split `request.total_amount` and record the three components on the row."""
    assert request.id is not None

    order = await session.get(Order, request.order_id)
    credit_funded, cash_funded = split_by_tender(
        request.total_amount,
        order_total=order.total if order else request.total_amount,
        store_credit_applied=order.store_credit_applied if order else 0.0,
    )

    wants_store_credit = (
        credit_funded > 0
        or request.settlement_choice == ReturnSettlementChoice.store_credit
    )
    # Locked FIRST — see the module docstring on lock ordering.
    account_credit = None
    if wants_store_credit:
        account_credit = await store_credit_svc.get_or_create_account(
            session,
            seller_profile_id=request.seller_profile_id,
            customer_profile_id=request.customer_profile_id,
            for_update=True,
        )

    reversal = 0.0
    remaining_cash = cash_funded
    payment = (
        await session.exec(select(Payment).where(Payment.order_id == request.order_id))
    ).first()
    if payment is not None and payment.method == PaymentMethod.Credit:
        account_debt = await credit_svc.lock_credit_account(
            session, request.seller_profile_id, request.customer_profile_id
        )
        if account_debt is not None and account_debt.outstanding_balance > 0:
            reversal = round(
                min(remaining_cash, account_debt.outstanding_balance), 2
            )
            if reversal > 0:
                await credit_svc.reverse_credit_charge(
                    session,
                    store_id=request.store_id,
                    customer_profile_id=request.customer_profile_id,
                    order_id=request.order_id,
                    amount=reversal,
                )
                remaining_cash = round(remaining_cash - reversal, 2)

    store_credit_amount = credit_funded
    payment_amount = 0.0
    if remaining_cash > 0:
        if request.settlement_choice == ReturnSettlementChoice.store_credit:
            store_credit_amount = round(store_credit_amount + remaining_cash, 2)
        else:
            payment_amount = remaining_cash

    if store_credit_amount > 0:
        if account_credit is None:  # only reachable if credit_funded was 0
            account_credit = await store_credit_svc.get_or_create_account(
                session,
                seller_profile_id=request.seller_profile_id,
                customer_profile_id=request.customer_profile_id,
                for_update=True,
            )
        await store_credit_svc.grant(
            session, account_credit, store_credit_amount,
            entry_type=StoreCreditEntryType.return_credit,
            return_request_id=request.id,
            note=f"return #{request.id}",
            actor_user_id=actor_user_id,
        )

    # Nothing left to hand over closes the return even if the customer asked
    # for money back.
    next_status = (
        ReturnStatus.awaiting_payment_confirmation
        if payment_amount > 0
        else ReturnStatus.closed
    )

    request.credit_reversal_amount = reversal
    request.store_credit_amount = store_credit_amount
    request.payment_amount = payment_amount
    session.add(request)
    await session.flush()

    total = round(reversal + store_credit_amount + payment_amount, 2)
    assert total == round(request.total_amount, 2), (
        f"settlement {total} != return total {request.total_amount}"
    )

    return SettlementResult(
        credit_reversal_amount=reversal,
        store_credit_amount=store_credit_amount,
        payment_amount=payment_amount,
        next_status=next_status,
    )
