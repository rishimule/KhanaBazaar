# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""order_receipt constraints (spec 2026-10-10 §2.1)."""
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.receipt import OrderReceipt, OrderReceiptCounter

# Reuse the order harness (autouse seed fixture: two stores, one customer).
from tests.test_orders import (  # noqa: F401
    _order_id_for_store,
    _place_orders,
    as_customer,
    seed,
)

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)


def _receipt(order_id: int, store_id: int, seq: int) -> OrderReceipt:
    return OrderReceipt(
        order_id=order_id,
        store_id=store_id,
        fiscal_year=2026,
        seq=seq,
        number=f"RC-2627-{seq:06d}",
        issued_at=NOW,
        issued_via="delivery",
        snapshot_version=1,
        snapshot={"version": 1},
    )


async def test_receipt_round_trips(as_customer: Any, seed: dict[str, int], session: AsyncSession) -> None:
    order_ids = await _place_orders(seed)
    order_a = await _order_id_for_store(order_ids, seed["store_a"])
    session.add(_receipt(order_a, seed["store_a"], 1))
    session.add(OrderReceiptCounter(store_id=seed["store_a"], fiscal_year=2026, last_seq=1))
    await session.commit()
    session.expunge_all()

    stored = await session.get(OrderReceipt, 1)
    assert stored is not None
    assert stored.number == "RC-2627-000001"
    assert stored.issued_at == NOW
    assert stored.snapshot == {"version": 1}
    counter = await session.get(OrderReceiptCounter, (seed["store_a"], 2026))
    assert counter is not None and counter.last_seq == 1


async def test_one_receipt_per_order(as_customer: Any, seed: dict[str, int], session: AsyncSession) -> None:
    order_ids = await _place_orders(seed)
    order_a = await _order_id_for_store(order_ids, seed["store_a"])
    session.add(_receipt(order_a, seed["store_a"], 1))
    await session.commit()
    session.add(_receipt(order_a, seed["store_a"], 2))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_seq_is_unique_per_store_and_year(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    order_a = await _order_id_for_store(order_ids, seed["store_a"])
    order_b = await _order_id_for_store(order_ids, seed["store_b"])
    # The same seq in another store's series is fine…
    session.add(_receipt(order_a, seed["store_a"], 1))
    session.add(_receipt(order_b, seed["store_b"], 1))
    await session.commit()
    # …and so is the same seq in another year of the same store…
    other_year = await session.get(OrderReceipt, 2)
    assert other_year is not None
    await session.delete(other_year)
    await session.commit()
    next_year = _receipt(order_b, seed["store_a"], 1)
    next_year.fiscal_year = 2027
    session.add(next_year)
    await session.commit()
    # …but not twice in one store's year.
    await session.delete(next_year)
    await session.commit()
    session.add(_receipt(order_b, seed["store_a"], 1))
    with pytest.raises(IntegrityError):
        await session.commit()
