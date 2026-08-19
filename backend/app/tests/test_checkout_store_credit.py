# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Spending customer store credit at checkout.

Reuses `tests.test_credit_checkout._seed`, which builds a cart worth 100.0 with
zero delivery fee, so the arithmetic in these tests is easy to follow.
"""
from typing import Any

import pytest
from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Order, Payment, PaymentMethod
from app.models.credit import CreditAccount
from app.models.profile import CustomerAddress
from app.models.returns import CustomerStoreCreditEntry, StoreCreditEntryType
from app.services import customer_store_credit as store_credit_svc
from app.services.checkout import place_order_for_sub_basket
from tests.test_credit_checkout import _seed


async def _grant(session: AsyncSession, seed: dict[str, Any], amount: float) -> None:
    account = await store_credit_svc.get_or_create_account(
        session,
        seller_profile_id=seed["seller_profile_id"],
        customer_profile_id=seed["customer_profile_id"],
    )
    await store_credit_svc.grant(
        session, account, amount, entry_type=StoreCreditEntryType.return_credit
    )
    await session.commit()


async def _customer_address_id(session: AsyncSession, seed: dict[str, Any]) -> int:
    """`_seed` returns the Address id, but checkout resolves a CustomerAddress
    id. The two coincide only for the first seed in a test, so look it up."""
    row = (
        await session.exec(
            select(CustomerAddress.id).where(
                CustomerAddress.customer_profile_id == seed["customer_profile_id"]
            )
        )
    ).first()
    assert row is not None
    return int(row)


async def _place(
    session: AsyncSession, seed: dict[str, Any], **kwargs: Any
) -> Order:
    return await place_order_for_sub_basket(
        session, seed["user"],
        customer_address_id=await _customer_address_id(session, seed),
        store_id=seed["store_id"], service_id=seed["service_id"],
        payment_method=kwargs.pop("payment_method", PaymentMethod.Upi),
        **kwargs,
    )


async def test_credit_reduces_the_payable_amount(session: AsyncSession) -> None:
    seed = await _seed(session)
    await _grant(session, seed, 40.0)

    order = await _place(session, seed)

    assert order.total == 100.0  # gross cost of the goods is unchanged
    assert order.store_credit_applied == 40.0
    payment = (
        await session.exec(select(Payment).where(Payment.order_id == order.id))
    ).one()
    assert payment.amount == 60.0

    entries = (
        await session.exec(
            select(CustomerStoreCreditEntry).where(
                CustomerStoreCreditEntry.entry_type == StoreCreditEntryType.order_applied
            )
        )
    ).all()
    assert len(entries) == 1
    assert entries[0].amount == -40.0
    assert entries[0].order_id == order.id


async def test_application_is_capped_at_the_order_total(session: AsyncSession) -> None:
    seed = await _seed(session)
    await _grant(session, seed, 900.0)

    order = await _place(session, seed)

    assert order.store_credit_applied == 100.0
    payment = (
        await session.exec(select(Payment).where(Payment.order_id == order.id))
    ).one()
    assert payment.amount == 0.0

    account = await store_credit_svc.get_or_create_account(
        session, seller_profile_id=seed["seller_profile_id"],
        customer_profile_id=seed["customer_profile_id"],
    )
    assert account.balance == 800.0


async def test_opting_out_leaves_the_credit_alone(session: AsyncSession) -> None:
    seed = await _seed(session)
    await _grant(session, seed, 40.0)

    order = await _place(session, seed, apply_store_credit=False)

    assert order.store_credit_applied == 0.0
    account = await store_credit_svc.get_or_create_account(
        session, seller_profile_id=seed["seller_profile_id"],
        customer_profile_id=seed["customer_profile_id"],
    )
    assert account.balance == 40.0
    assert (
        await session.exec(
            select(CustomerStoreCreditEntry).where(
                CustomerStoreCreditEntry.entry_type == StoreCreditEntryType.order_applied
            )
        )
    ).all() == []


async def test_credit_is_scoped_to_the_seller(session: AsyncSession) -> None:
    """Credit with seller A must not spend on seller B's order."""
    seller_a = await _seed(session)
    seller_b = await _seed(session)
    # Grant against A's seller but B's customer profile — different pair entirely.
    account = await store_credit_svc.get_or_create_account(
        session, seller_profile_id=seller_a["seller_profile_id"],
        customer_profile_id=seller_a["customer_profile_id"],
    )
    await store_credit_svc.grant(
        session, account, 75.0, entry_type=StoreCreditEntryType.return_credit
    )
    await session.commit()

    order = await _place(session, seller_b)
    assert order.store_credit_applied == 0.0


async def test_no_account_means_no_discount(session: AsyncSession) -> None:
    seed = await _seed(session)
    order = await _place(session, seed)
    assert order.store_credit_applied == 0.0


async def test_postpaid_credit_borrows_only_the_remainder(
    session: AsyncSession,
) -> None:
    seed = await _seed(session, credit_limit=2000.0)
    await _grant(session, seed, 40.0)

    order = await _place(session, seed, payment_method=PaymentMethod.Credit)

    assert order.store_credit_applied == 40.0
    account = (
        await session.exec(
            select(CreditAccount).where(
                CreditAccount.seller_profile_id == seed["seller_profile_id"]
            )
        )
    ).one()
    assert account.outstanding_balance == 60.0


async def test_eligibility_is_measured_after_store_credit(
    session: AsyncSession,
) -> None:
    """Limit 70, order 100, store credit 40 → payable 60 ≤ 70, so this MUST
    succeed. Checking eligibility against the gross total would wrongly 409."""
    seed = await _seed(session, credit_limit=70.0)
    await _grant(session, seed, 40.0)

    order = await _place(session, seed, payment_method=PaymentMethod.Credit)
    assert order.store_credit_applied == 40.0


async def test_insufficient_postpaid_credit_still_blocks(
    session: AsyncSession,
) -> None:
    seed = await _seed(session, credit_limit=50.0)
    await _grant(session, seed, 10.0)  # payable 90 > 50

    with pytest.raises(HTTPException) as exc:
        await _place(session, seed, payment_method=PaymentMethod.Credit)
    assert exc.value.status_code == 409


async def test_cancelling_an_order_returns_the_credit(session: AsyncSession) -> None:
    from app.models.base import UserRole
    from app.services.orders import cancel_order

    seed = await _seed(session)
    await _grant(session, seed, 40.0)
    order = await _place(session, seed)
    assert order.store_credit_applied == 40.0

    actor = seed["user"]
    actor.role = UserRole.Customer
    await cancel_order(session, order, actor)

    account = await store_credit_svc.get_or_create_account(
        session, seller_profile_id=seed["seller_profile_id"],
        customer_profile_id=seed["customer_profile_id"],
    )
    assert account.balance == 40.0
    reverted = (
        await session.exec(
            select(CustomerStoreCreditEntry).where(
                CustomerStoreCreditEntry.entry_type
                == StoreCreditEntryType.order_reverted
            )
        )
    ).all()
    assert len(reverted) == 1
    assert reverted[0].amount == 40.0


async def test_cancel_reverses_only_what_was_borrowed(session: AsyncSession) -> None:
    """Regression: cancel reversed the GROSS total while checkout had charged
    only the post-credit remainder, so a mixed-tender order refunded the credit
    portion twice and ate unrelated debt."""
    from app.models.base import UserRole
    from app.services.orders import cancel_order

    seed = await _seed(session, credit_limit=2000.0, outstanding=300.0)
    await _grant(session, seed, 40.0)

    order = await _place(session, seed, payment_method=PaymentMethod.Credit)
    assert order.store_credit_applied == 40.0
    account = (
        await session.exec(
            select(CreditAccount).where(
                CreditAccount.seller_profile_id == seed["seller_profile_id"]
            )
        )
    ).one()
    # 300 prior debt + 60 borrowed (100 order - 40 store credit)
    assert account.outstanding_balance == 360.0

    actor = seed["user"]
    actor.role = UserRole.Customer
    await cancel_order(session, order, actor)

    await session.refresh(account)
    # Back to the prior debt exactly. Reversing the gross 100 would leave 260,
    # silently erasing 40 of unrelated debt.
    assert account.outstanding_balance == 300.0
    credit_account = await store_credit_svc.get_or_create_account(
        session, seller_profile_id=seed["seller_profile_id"],
        customer_profile_id=seed["customer_profile_id"],
    )
    assert credit_account.balance == 40.0
