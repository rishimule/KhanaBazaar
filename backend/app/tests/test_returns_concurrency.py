# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Concurrency on the settlement and line-locking paths.

`override_get_db_session` builds a fresh AsyncSession per request on a NullPool
engine, so `asyncio.gather` over two client calls produces two genuinely
overlapping Postgres transactions — enough to exercise the `FOR UPDATE` locks
that guard settlement. Without them a double-clicked Accept would settle twice.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.returns import (
    CustomerStoreCredit,
    CustomerStoreCreditEntry,
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
    StoreCreditEntryType,
)
from tests._returns_helpers import (
    as_customer,
    as_seller,
    clear_overrides,
    publish_return_agreement,
    seed_delivered_order,
)


async def _active_return(
    session: AsyncSession, seed: object, *, otp: str = "424242"
) -> int:
    """An `active` return holding both lines, with a known handover code."""
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id,                       # type: ignore[attr-defined]
        customer_profile_id=seed.customer_profile_id, # type: ignore[attr-defined]
        store_id=seed.store_id,                       # type: ignore[attr-defined]
        seller_profile_id=seed.seller_profile_id,     # type: ignore[attr-defined]
        service_id=seed.service_id,                   # type: ignore[attr-defined]
        initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user.id,   # type: ignore[attr-defined]
        status=ReturnStatus.active,
        is_full_order=False,
        reason_code=ReturnReasonCode.damaged,
        items_amount=250.0, delivery_fee_amount=0.0, total_amount=250.0,
        settlement_choice=ReturnSettlementChoice.store_credit,
        agreement_policy_version=1,
        agreement_accepted_at=now,
        window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48),
        handover_expires_at=now + timedelta(days=7),
        receipt_otp=otp,
        confirmed_at=now,
    )
    session.add(req)
    await session.flush()
    session.add(
        ReturnRequestItem(
            return_request_id=req.id,
            order_item_id=seed.order_item_ids[0],      # type: ignore[attr-defined]
            quantity=1, product_name_snapshot="Ghee 1L",
            unit_price_snapshot=250.0, line_total=250.0,
        )
    )
    await session.commit()
    assert req.id is not None
    return req.id


async def test_concurrent_accepts_settle_exactly_once(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, line_specs=[("Ghee 1L", 250.0, 1)])
    return_id = await _active_return(session, seed)
    as_seller(seed.seller_user)
    try:
        results = await asyncio.gather(
            client.post(
                f"/api/v1/sellers/me/returns/{return_id}/accept",
                json={"otp": "424242", "restock": False},
            ),
            client.post(
                f"/api/v1/sellers/me/returns/{return_id}/accept",
                json={"otp": "424242", "restock": False},
            ),
            return_exceptions=True,
        )
    finally:
        clear_overrides()

    for r in results:
        assert not isinstance(r, BaseException), f"request raised: {r!r}"
    codes = [r.status_code for r in results]
    assert len(codes) == 2
    assert codes.count(200) == 1, f"expected exactly one winner, got {codes}"
    assert any(c != 200 for c in codes), codes

    # The money must have moved once and only once.
    entries = (
        await session.exec(
            select(CustomerStoreCreditEntry).where(
                CustomerStoreCreditEntry.entry_type
                == StoreCreditEntryType.return_credit
            )
        )
    ).all()
    assert len(entries) == 1, f"settled {len(entries)} times"
    account = (await session.exec(select(CustomerStoreCredit))).one()
    assert account.balance == 250.0
    assert account.lifetime_earned == 250.0

    fresh = await session.get(ReturnRequest, return_id)
    assert fresh is not None
    await session.refresh(fresh)
    assert fresh.status == ReturnStatus.closed
    assert fresh.store_credit_amount == 250.0


async def test_concurrent_accept_and_withdraw_cannot_both_win(
    session: AsyncSession, client: AsyncClient
) -> None:
    """A customer withdrawing while the seller accepts must not release the
    lines after the credit was granted."""
    seed = await seed_delivered_order(session, line_specs=[("Ghee 1L", 250.0, 1)])
    return_id = await _active_return(session, seed)

    from app import app as fastapi_app
    from app.core.security import (
        get_current_customer,
        get_current_seller,
        get_current_user,
    )

    # Both roles overridden at once so the two calls authenticate concurrently.
    fastapi_app.dependency_overrides[get_current_seller] = lambda: seed.seller_user
    fastapi_app.dependency_overrides[get_current_customer] = lambda: seed.customer_user
    fastapi_app.dependency_overrides[get_current_user] = lambda: seed.customer_user
    try:
        accept, withdraw = await asyncio.gather(
            client.post(
                f"/api/v1/sellers/me/returns/{return_id}/accept",
                json={"otp": "424242", "restock": False},
            ),
            client.post(f"/api/v1/returns/{return_id}/withdraw"),
            return_exceptions=True,
        )
    finally:
        clear_overrides()

    for r in (accept, withdraw):
        assert not isinstance(r, BaseException), f"request raised: {r!r}"
    codes = [accept.status_code, withdraw.status_code]
    assert codes.count(200) <= 1, f"both transitions won: {codes}"

    fresh = await session.get(ReturnRequest, return_id)
    assert fresh is not None
    await session.refresh(fresh)
    entries = (await session.exec(select(CustomerStoreCreditEntry))).all()
    if fresh.status == ReturnStatus.closed:
        # Accept won: credit granted, lines stay locked.
        assert len(entries) == 1
    else:
        # Withdraw won: nothing settled.
        assert fresh.status == ReturnStatus.withdrawn
        assert entries == []


async def test_concurrent_creates_cannot_double_lock_a_line(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Two return requests racing on the same order line: one must lose."""
    seed = await seed_delivered_order(session, line_specs=[("Ghee 1L", 250.0, 1)])
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    body = {
        "order_id": seed.order_id,
        "order_item_ids": [seed.order_item_ids[0]],
        "reason_code": "damaged",
        "reason_note": None,
        "settlement_choice": "store_credit",
    }
    try:
        results = await asyncio.gather(
            client.post("/api/v1/returns", json=body),
            client.post("/api/v1/returns", json=body),
            return_exceptions=True,
        )
    finally:
        clear_overrides()

    for r in results:
        assert not isinstance(r, BaseException), f"request raised: {r!r}"
    codes = [r.status_code for r in results]
    assert len(codes) == 2
    assert codes.count(201) == 1, f"expected one create to win, got {codes}"

    rows = (await session.exec(select(ReturnRequest))).all()
    assert len(rows) == 1, f"{len(rows)} returns hold the same line"
