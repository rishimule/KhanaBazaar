# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.returns import (
    CustomerStoreCredit,
    CustomerStoreCreditEntry,
    StoreCreditEntryType,
)
from app.services import customer_store_credit as svc
from tests._returns_helpers import SeededOrder, seed_delivered_order


async def _seed(session: AsyncSession) -> SeededOrder:
    return await seed_delivered_order(session)


async def test_get_or_create_is_idempotent(session: AsyncSession) -> None:
    seed = await _seed(session)
    seller, customer = seed.seller_profile_id, seed.customer_profile_id
    a = await svc.get_or_create_account(
        session, seller_profile_id=seller, customer_profile_id=customer
    )
    await session.commit()
    b = await svc.get_or_create_account(
        session, seller_profile_id=seller, customer_profile_id=customer
    )
    await session.commit()
    assert a.id == b.id
    rows = (await session.exec(select(CustomerStoreCredit))).all()
    assert len(rows) == 1


async def test_grant_raises_balance_and_writes_ledger(session: AsyncSession) -> None:
    seed = await _seed(session)
    seller, customer = seed.seller_profile_id, seed.customer_profile_id
    acct = await svc.get_or_create_account(
        session, seller_profile_id=seller, customer_profile_id=customer
    )
    entry = await svc.grant(
        session, acct, 120.0,
        entry_type=StoreCreditEntryType.return_credit, note="return #1",
    )
    await session.commit()

    assert acct.balance == 120.0
    assert acct.lifetime_earned == 120.0
    assert acct.lifetime_spent == 0.0
    assert entry.amount == 120.0
    assert entry.balance_after == 120.0


async def test_grant_rejects_non_positive(session: AsyncSession) -> None:
    seed = await _seed(session)
    seller, customer = seed.seller_profile_id, seed.customer_profile_id
    acct = await svc.get_or_create_account(
        session, seller_profile_id=seller, customer_profile_id=customer
    )
    with pytest.raises(svc.StoreCreditError):
        await svc.grant(session, acct, 0.0, entry_type=StoreCreditEntryType.return_credit)
    with pytest.raises(svc.StoreCreditError):
        await svc.grant(session, acct, -5.0, entry_type=StoreCreditEntryType.return_credit)


async def test_spend_clamps_to_balance(session: AsyncSession) -> None:
    seed = await _seed(session)
    seller, customer = seed.seller_profile_id, seed.customer_profile_id
    acct = await svc.get_or_create_account(
        session, seller_profile_id=seller, customer_profile_id=customer
    )
    await svc.grant(session, acct, 50.0, entry_type=StoreCreditEntryType.return_credit)
    applied = await svc.spend(session, acct, 120.0, order_id=seed.order_id)
    await session.commit()

    assert applied == 50.0
    assert acct.balance == 0.0
    assert acct.lifetime_spent == 50.0
    entries = (await session.exec(
        select(CustomerStoreCreditEntry).where(
            CustomerStoreCreditEntry.entry_type == StoreCreditEntryType.order_applied
        )
    )).all()
    assert entries[0].amount == -50.0
    assert entries[0].balance_after == 0.0


async def test_spend_on_empty_balance_is_a_noop(session: AsyncSession) -> None:
    seed = await _seed(session)
    seller, customer = seed.seller_profile_id, seed.customer_profile_id
    acct = await svc.get_or_create_account(
        session, seller_profile_id=seller, customer_profile_id=customer
    )
    applied = await svc.spend(session, acct, 40.0, order_id=seed.order_id)
    await session.commit()
    assert applied == 0.0
    assert (await session.exec(select(CustomerStoreCreditEntry))).all() == []


async def test_revert_order_returns_the_credit(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session)
    acct = await svc.get_or_create_account(
        session, seller_profile_id=seed.seller_profile_id,
        customer_profile_id=seed.customer_profile_id,
    )
    await svc.grant(session, acct, 100.0, entry_type=StoreCreditEntryType.return_credit)
    await svc.spend(session, acct, 60.0, order_id=seed.order_id)
    await session.commit()

    await svc.revert_order(
        session, seller_profile_id=seed.seller_profile_id,
        customer_profile_id=seed.customer_profile_id,
        order_id=seed.order_id, amount=60.0,
    )
    await session.commit()
    await session.refresh(acct)

    assert acct.balance == 100.0
    # lifetime_spent unwinds too, so the display figure stays honest.
    assert acct.lifetime_spent == 0.0


async def test_revert_without_an_account_is_a_noop(session: AsyncSession) -> None:
    """A cancelled order that never spent credit must not create an account."""
    seed = await seed_delivered_order(session)
    await svc.revert_order(
        session, seller_profile_id=seed.seller_profile_id,
        customer_profile_id=seed.customer_profile_id,
        order_id=seed.order_id, amount=25.0,
    )
    await session.commit()
    assert (await session.exec(select(CustomerStoreCredit))).all() == []


async def test_balances_are_isolated_per_seller(session: AsyncSession) -> None:
    one = await seed_delivered_order(session, email_suffix="a")
    two = await seed_delivered_order(session, email_suffix="b")
    a1 = await svc.get_or_create_account(
        session, seller_profile_id=one.seller_profile_id,
        customer_profile_id=one.customer_profile_id,
    )
    a2 = await svc.get_or_create_account(
        session, seller_profile_id=two.seller_profile_id,
        customer_profile_id=one.customer_profile_id,
    )
    await svc.grant(session, a1, 100.0, entry_type=StoreCreditEntryType.return_credit)
    await session.commit()

    assert a2.balance == 0.0
    balances = await svc.list_balances(session, one.customer_profile_id)
    assert {b.seller_profile_id: b.balance for b in balances} == {
        one.seller_profile_id: 100.0, two.seller_profile_id: 0.0
    }


async def test_amounts_are_rounded_to_paise(session: AsyncSession) -> None:
    seed = await _seed(session)
    seller, customer = seed.seller_profile_id, seed.customer_profile_id
    acct = await svc.get_or_create_account(
        session, seller_profile_id=seller, customer_profile_id=customer
    )
    await svc.grant(session, acct, 0.1, entry_type=StoreCreditEntryType.return_credit)
    await svc.grant(session, acct, 0.2, entry_type=StoreCreditEntryType.return_credit)
    await session.commit()
    assert acct.balance == 0.3


async def test_ledger_is_ordered_newest_first(session: AsyncSession) -> None:
    seed = await _seed(session)
    seller, customer = seed.seller_profile_id, seed.customer_profile_id
    acct = await svc.get_or_create_account(
        session, seller_profile_id=seller, customer_profile_id=customer
    )
    await svc.grant(session, acct, 10.0, entry_type=StoreCreditEntryType.return_credit, note="first")
    await svc.grant(session, acct, 20.0, entry_type=StoreCreditEntryType.admin_adjust, note="second")
    await session.commit()

    assert acct.id is not None
    entries = await svc.list_entries(session, acct.id)
    assert [e.balance_after for e in entries] == [30.0, 10.0]
