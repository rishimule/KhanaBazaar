# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import PaymentMethod
from app.models.credit import CreditAccount, CreditEntryType, CreditLedgerEntry
from app.models.returns import (
    CustomerStoreCredit,
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnSettlementChoice,
    ReturnStatus,
)
from app.services.return_settlement import settle
from tests._returns_helpers import seed_delivered_order


async def _request(
    session: AsyncSession, seed: Any, *, total: float, choice: ReturnSettlementChoice
) -> ReturnRequest:
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id, status=ReturnStatus.active,
        is_full_order=True, reason_code=ReturnReasonCode.damaged,
        items_amount=total, delivery_fee_amount=0.0, total_amount=total,
        settlement_choice=choice, agreement_policy_version=1,
        window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48),
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def _credit_account(
    session: AsyncSession, seed: Any, *, outstanding: float
) -> CreditAccount:
    acct = CreditAccount(
        seller_profile_id=seed.seller_profile_id,
        customer_profile_id=seed.customer_profile_id,
        credit_limit=5000.0, outstanding_balance=outstanding, granted_by_user_id=1,
    )
    session.add(acct)
    await session.commit()
    await session.refresh(acct)
    return acct


async def test_store_credit_only_closes_immediately(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session)
    req = await _request(
        session, seed, total=300.0, choice=ReturnSettlementChoice.store_credit
    )

    result = await settle(session, req, actor_user_id=seed.customer_user_id)
    await session.commit()

    assert result.credit_reversal_amount == 0.0
    assert result.store_credit_amount == 300.0
    assert result.payment_amount == 0.0
    assert result.next_status == ReturnStatus.closed

    acct = (await session.exec(select(CustomerStoreCredit))).first()
    assert acct is not None
    assert acct.balance == 300.0


async def test_payment_choice_parks_for_confirmation(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session)
    req = await _request(
        session, seed, total=300.0, choice=ReturnSettlementChoice.payment
    )

    result = await settle(session, req, actor_user_id=seed.customer_user_id)
    await session.commit()

    assert result.payment_amount == 300.0
    assert result.next_status == ReturnStatus.awaiting_payment_confirmation
    # No store-credit account is created for a cash settlement.
    assert (await session.exec(select(CustomerStoreCredit))).first() is None


async def test_credit_order_reverses_debt_first(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session, payment_method=PaymentMethod.Credit)
    await _credit_account(session, seed, outstanding=1000.0)
    req = await _request(
        session, seed, total=300.0, choice=ReturnSettlementChoice.payment
    )

    result = await settle(session, req, actor_user_id=seed.customer_user_id)
    await session.commit()

    assert result.credit_reversal_amount == 300.0
    assert result.payment_amount == 0.0
    # Fully absorbed by the reversal: nothing to hand over, so it closes even
    # though the customer asked for money back.
    assert result.next_status == ReturnStatus.closed

    acct = (await session.exec(select(CreditAccount))).first()
    assert acct is not None
    assert acct.outstanding_balance == 700.0
    entry = (await session.exec(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.entry_type == CreditEntryType.reversal
        )
    )).first()
    assert entry is not None
    assert entry.amount == 300.0


async def test_reversal_is_capped_at_outstanding_and_remainder_splits(
    session: AsyncSession,
) -> None:
    """Bought on credit, partly repaid, returns everything: the debt is wiped
    and the rest becomes store credit."""
    seed = await seed_delivered_order(session, payment_method=PaymentMethod.Credit)
    await _credit_account(session, seed, outstanding=120.0)
    req = await _request(
        session, seed, total=500.0, choice=ReturnSettlementChoice.store_credit
    )

    result = await settle(session, req, actor_user_id=seed.customer_user_id)
    await session.commit()

    assert result.credit_reversal_amount == 120.0
    assert result.store_credit_amount == 380.0
    assert result.next_status == ReturnStatus.closed
    acct = (await session.exec(select(CreditAccount))).first()
    assert acct is not None
    assert acct.outstanding_balance == 0.0


async def test_reversal_remainder_can_park_for_payment(
    session: AsyncSession,
) -> None:
    seed = await seed_delivered_order(session, payment_method=PaymentMethod.Credit)
    await _credit_account(session, seed, outstanding=120.0)
    req = await _request(
        session, seed, total=500.0, choice=ReturnSettlementChoice.payment
    )

    result = await settle(session, req, actor_user_id=seed.customer_user_id)
    await session.commit()

    assert result.credit_reversal_amount == 120.0
    assert result.payment_amount == 380.0
    assert result.next_status == ReturnStatus.awaiting_payment_confirmation


async def test_credit_order_with_no_outstanding_uses_the_chosen_path(
    session: AsyncSession,
) -> None:
    seed = await seed_delivered_order(session, payment_method=PaymentMethod.Credit)
    await _credit_account(session, seed, outstanding=0.0)
    req = await _request(
        session, seed, total=200.0, choice=ReturnSettlementChoice.payment
    )

    result = await settle(session, req, actor_user_id=seed.customer_user_id)
    await session.commit()

    assert result.credit_reversal_amount == 0.0
    assert result.payment_amount == 200.0
    assert result.next_status == ReturnStatus.awaiting_payment_confirmation


async def test_credit_order_without_an_account_falls_through(
    session: AsyncSession,
) -> None:
    """A credit-method order whose account was since deleted must still settle."""
    seed = await seed_delivered_order(session, payment_method=PaymentMethod.Credit)
    req = await _request(
        session, seed, total=200.0, choice=ReturnSettlementChoice.store_credit
    )

    result = await settle(session, req, actor_user_id=seed.customer_user_id)
    await session.commit()

    assert result.credit_reversal_amount == 0.0
    assert result.store_credit_amount == 200.0


async def test_non_credit_order_never_touches_the_credit_ledger(
    session: AsyncSession,
) -> None:
    """A UPI order must not reverse debt even if the customer happens to owe
    this seller from a different order."""
    seed = await seed_delivered_order(session, payment_method=PaymentMethod.Upi)
    await _credit_account(session, seed, outstanding=900.0)
    req = await _request(
        session, seed, total=200.0, choice=ReturnSettlementChoice.payment
    )

    result = await settle(session, req, actor_user_id=seed.customer_user_id)
    await session.commit()

    assert result.credit_reversal_amount == 0.0
    acct = (await session.exec(select(CreditAccount))).first()
    assert acct is not None
    assert acct.outstanding_balance == 900.0


async def test_amounts_always_sum_to_the_total(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session, payment_method=PaymentMethod.Credit)
    await _credit_account(session, seed, outstanding=33.33)
    req = await _request(
        session, seed, total=99.99, choice=ReturnSettlementChoice.store_credit
    )

    result = await settle(session, req, actor_user_id=seed.customer_user_id)
    await session.commit()

    total = round(
        result.credit_reversal_amount
        + result.store_credit_amount
        + result.payment_amount,
        2,
    )
    assert total == 99.99
    assert req.credit_reversal_amount == result.credit_reversal_amount
    assert req.store_credit_amount == result.store_credit_amount
    assert req.payment_amount == result.payment_amount
