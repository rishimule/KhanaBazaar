# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Backfill + repair sweep (spec 2026-10-10 §7)."""
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import patch

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import (
    Delivery,
    DeliveryStatus,
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.profile import CustomerAddress
from app.models.receipt import OrderReceipt
from app.services import receipts as receipts_svc
from app.services.receipts import issue_missing
from tests.test_orders import as_customer, seed  # noqa: F401

UTC = timezone.utc


async def _delivered_order(
    session: AsyncSession,
    seed: dict[str, int],
    *,
    delivered_at: Optional[datetime],
    placed_at: datetime = datetime(2026, 9, 1, tzinfo=UTC),
) -> int:
    """A delivered store_a order with no receipt, as history looks before release."""
    link = await session.get(CustomerAddress, seed["customer_address_id"])
    assert link is not None
    order = Order(
        customer_profile_id=seed["customer_profile"],
        store_id=seed["store_a"],
        service_id=seed["grocery_service_id"],
        service_name_snapshot="Grocery",
        delivery_address_id=link.address_id,
        delivery_address_snapshot="1 Test Street, Bengaluru 560050",
        status=OrderStatus.Delivered,
        subtotal=50.0,
        delivery_fee=0.0,
        tax=0.0,
        total=50.0,
        placed_at=placed_at,
    )
    session.add(order)
    await session.flush()
    assert order.id is not None
    order_id = order.id
    session.add_all(
        [
            Delivery(order_id=order_id, status=DeliveryStatus.Delivered, delivered_at=delivered_at),
            Payment(
                order_id=order_id,
                amount=50.0,
                method=PaymentMethod.Upi,
                status=PaymentStatus.Paid,
                paid_at=delivered_at,
            ),
        ]
    )
    await session.commit()
    return order_id


async def _numbers(session: AsyncSession) -> dict[int, str]:
    rows = (await session.exec(select(OrderReceipt).order_by(col(OrderReceipt.id)))).all()
    return {r.order_id: r.number for r in rows}


async def test_backfill_numbers_history_in_delivery_order(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    third = await _delivered_order(session, seed, delivered_at=datetime(2026, 10, 3, tzinfo=UTC))
    first = await _delivered_order(session, seed, delivered_at=datetime(2026, 10, 1, tzinfo=UTC))
    second = await _delivered_order(session, seed, delivered_at=datetime(2026, 10, 2, tzinfo=UTC))

    assert await issue_missing(session) == (3, 0)
    assert await _numbers(session) == {
        first: "RC-2627-000001",
        second: "RC-2627-000002",
        third: "RC-2627-000003",
    }
    receipt = (
        await session.exec(select(OrderReceipt).where(OrderReceipt.order_id == first))
    ).one()
    assert receipt.issued_via == "backfill"
    assert receipt.issued_at == datetime(2026, 10, 1, tzinfo=UTC)
    # Idempotent: a second run finds nothing.
    assert await issue_missing(session) == (0, 0)


async def test_backfill_splits_financial_years(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    march = await _delivered_order(
        session, seed, delivered_at=datetime(2026, 3, 31, 18, 0, tzinfo=UTC)  # 23:30 IST
    )
    april = await _delivered_order(session, seed, delivered_at=datetime(2026, 4, 2, tzinfo=UTC))
    await issue_missing(session)
    assert await _numbers(session) == {march: "RC-2526-000001", april: "RC-2627-000001"}


async def test_missing_delivered_at_falls_back_to_placed_at(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    placed = datetime(2026, 8, 15, 6, 0, tzinfo=UTC)
    oid = await _delivered_order(session, seed, delivered_at=None, placed_at=placed)
    await issue_missing(session)
    receipt = (await session.exec(select(OrderReceipt).where(OrderReceipt.order_id == oid))).one()
    assert receipt.issued_at == placed


async def test_one_bad_order_does_not_stop_the_rest(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    # The failing order is the oldest, so the loop must carry on after its
    # rollback (expired identity map, then session.get).
    bad = await _delivered_order(session, seed, delivered_at=datetime(2026, 10, 1, tzinfo=UTC))
    good = await _delivered_order(session, seed, delivered_at=datetime(2026, 10, 2, tzinfo=UTC))
    real_build = receipts_svc.build_snapshot

    def flaky(inputs: Any, *, delivered_at: datetime) -> Any:
        if inputs.order.id == bad:
            raise RuntimeError("boom")
        return real_build(inputs, delivered_at=delivered_at)

    with patch("app.services.receipts.build_snapshot", side_effect=flaky):
        assert await issue_missing(session) == (1, 1)
    assert set(await _numbers(session)) == {good}
    # The next run (bug fixed) picks the straggler up.
    assert await issue_missing(session) == (1, 0)
    assert set(await _numbers(session)) == {good, bad}


async def test_limit_takes_the_oldest(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    await _delivered_order(session, seed, delivered_at=datetime(2026, 10, 2, tzinfo=UTC))
    older = await _delivered_order(session, seed, delivered_at=datetime(2026, 10, 1, tzinfo=UTC))
    assert await issue_missing(session, limit=1) == (1, 0)
    assert set(await _numbers(session)) == {older}


async def test_hourly_task_runs_the_sweep(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    from app.worker import issue_missing_receipts

    oid = await _delivered_order(session, seed, delivered_at=datetime(2026, 10, 1, tzinfo=UTC))
    assert issue_missing_receipts() == 1
    assert oid in await _numbers(session)


async def test_backfill_script_fails_the_deploy_on_errors(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "backfill_order_receipts",
        Path(__file__).resolve().parents[1] / "scripts" / "backfill_order_receipts.py",
    )
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    await _delivered_order(session, seed, delivered_at=datetime(2026, 10, 1, tzinfo=UTC))
    with patch("app.services.receipts.build_snapshot", side_effect=RuntimeError("boom")):
        assert await script._main() == 1
    assert await script._main() == 0
