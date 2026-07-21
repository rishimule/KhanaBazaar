# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Store-level wallet-credit primitive: schema round-trip + service behaviour."""
import pytest
import pytest_asyncio
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import NotificationType
from app.models.platform_fee import StoreCreditEvent, StoreCreditReason
from app.models.store import Store
from app.services import store_credit


@pytest_asyncio.fixture
async def seeded_store(approved_seller_with_store):
    """The live Store owned by an approved seller (from the shared bundle)."""
    return approved_seller_with_store.store


@pytest.mark.asyncio
async def test_store_credit_columns_and_enum(session: AsyncSession, seeded_store) -> None:
    store = seeded_store
    store.fee_credit_balance = 42.0
    session.add(store)
    session.add(
        StoreCreditEvent(
            store_id=store.id, amount_delta=42.0,
            reason=StoreCreditReason.GrantedOnExit, actor="system",
        )
    )
    await session.commit()
    rows = (await session.exec(select(StoreCreditEvent))).all()
    assert len(rows) == 1 and rows[0].reason == StoreCreditReason.GrantedOnExit
    refreshed = await session.get(Store, store.id)
    assert refreshed.fee_credit_balance == 42.0
    assert NotificationType.FeeLowBalance.value == "fee_low_balance"


@pytest.mark.asyncio
async def test_grant_and_apply(session: AsyncSession, seeded_store) -> None:
    store = seeded_store
    await store_credit.grant(session, store, 100.0, actor="admin:1", note="goodwill")
    await session.commit()
    assert (await session.get(Store, store.id)).fee_credit_balance == 100.0

    applied = await store_credit.apply(session, store, 30.0, actor="seller")
    await session.commit()
    assert applied == 30.0
    assert (await session.get(Store, store.id)).fee_credit_balance == 70.0


@pytest.mark.asyncio
async def test_apply_clamps_to_balance(session: AsyncSession, seeded_store) -> None:
    store = seeded_store
    await store_credit.grant(session, store, 20.0, actor="admin:1")
    applied = await store_credit.apply(session, store, 50.0, actor="seller")
    await session.commit()
    assert applied == 20.0
    assert (await session.get(Store, store.id)).fee_credit_balance == 0.0


@pytest.mark.asyncio
async def test_cash_out_over_balance_rejected(session: AsyncSession, seeded_store) -> None:
    store = seeded_store
    await store_credit.grant(session, store, 10.0, actor="admin:1")
    with pytest.raises(store_credit.StoreCreditError):
        await store_credit.cash_out(session, store, 25.0, actor="admin:1", note="x")


@pytest.mark.asyncio
async def test_reconciliation_invariant(session: AsyncSession, seeded_store) -> None:
    store = seeded_store
    await store_credit.grant(session, store, 100.0, actor="admin:1")
    await store_credit.apply(session, store, 40.0, actor="seller")
    await store_credit.cash_out(session, store, 10.0, actor="admin:1", note="refund")
    await session.commit()
    total = (
        await session.exec(
            select(func.coalesce(func.sum(StoreCreditEvent.amount_delta), 0.0)).where(
                StoreCreditEvent.store_id == store.id
            )
        )
    ).one()
    assert float(total) == (await session.get(Store, store.id)).fee_credit_balance
