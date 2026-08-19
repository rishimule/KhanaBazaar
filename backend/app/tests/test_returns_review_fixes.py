# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Regression tests for defects found in code review.

Each test here maps to a specific finding; the comment names it so a future
reader knows what would break if the test is deleted.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User
from app.models.returns import (
    CustomerStoreCredit,
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
)
from app.services.returns import locked_order_item_ids
from tests._returns_helpers import (
    as_admin,
    as_customer,
    as_seller,
    clear_overrides,
    pk,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _return(
    session: AsyncSession,
    seed: Any,
    *,
    status: ReturnStatus,
    code: str | None = "111222",
) -> ReturnRequest:
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id, status=status,
        is_full_order=False, reason_code=ReturnReasonCode.damaged,
        items_amount=250.0, delivery_fee_amount=0.0, total_amount=250.0,
        payment_amount=(
            250.0 if status == ReturnStatus.awaiting_payment_confirmation else 0.0
        ),
        settlement_choice=ReturnSettlementChoice.store_credit,
        agreement_policy_version=1, window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48),
        handover_expires_at=(
            now + timedelta(days=5) if status == ReturnStatus.active else None
        ),
        receipt_otp=code if status == ReturnStatus.active else None,
        receipt_otp_sent_at=now - timedelta(minutes=5),
    )
    session.add(req)
    await session.flush()
    session.add(ReturnRequestItem(
        return_request_id=req.id, order_item_id=seed.order_item_ids[0], quantity=1,
        product_name_snapshot="Ghee 1L", unit_price_snapshot=250.0, line_total=250.0,
    ))
    await session.commit()
    await session.refresh(req)
    return req


# ─── Finding: force-close fabricated an accepted return ──────────────────


async def test_force_close_on_an_unconfirmed_return_withdraws_it(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    """Marking it `closed` would record a return the customer never consented
    to, lock the lines forever and block any retry on that order."""
    seed = await seed_delivered_order(session)
    req = await _return(
        session, seed, status=ReturnStatus.awaiting_customer_confirmation
    )
    as_admin(admin_user)

    resp = await client.post(
        f"/api/v1/admin/returns/{pk(req.id)}/close",
        json={"reason": "customer never confirmed and has gone quiet"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "withdrawn"
    # Nothing was settled...
    assert resp.json()["store_credit_amount"] == 0.0
    assert resp.json()["credit_reversal_amount"] == 0.0
    assert (await session.exec(select(CustomerStoreCredit))).first() is None
    # ...and the lines are free for a real return.
    session.expunge_all()
    assert await locked_order_item_ids(session, seed.order_id) == set()


async def test_force_close_on_an_active_return_withdraws_it(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    seed = await seed_delivered_order(session)
    req = await _return(session, seed, status=ReturnStatus.active)
    as_admin(admin_user)

    resp = await client.post(
        f"/api/v1/admin/returns/{pk(req.id)}/close",
        json={"reason": "goods were never brought to the store"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "withdrawn"
    session.expunge_all()
    assert await locked_order_item_ids(session, seed.order_id) == set()


async def test_force_close_still_closes_an_awaiting_payment_return(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    """The genuine case: money moved offline and nobody confirmed."""
    seed = await seed_delivered_order(session)
    req = await _return(
        session, seed, status=ReturnStatus.awaiting_payment_confirmation
    )
    as_admin(admin_user)

    resp = await client.post(
        f"/api/v1/admin/returns/{pk(req.id)}/close",
        json={"reason": "cash settled at the counter, customer went quiet"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"
    # An accepted return keeps its lines locked — they really did go back.
    session.expunge_all()
    assert await locked_order_item_ids(session, seed.order_id) == {
        seed.order_item_ids[0]
    }


# ─── Finding: a mistyped handover code bricked the return ────────────────


async def test_receipt_code_can_be_reissued_after_failed_attempts(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _return(session, seed, status=ReturnStatus.active)

    as_seller(seed.seller_user)
    for _ in range(5):
        await client.post(
            f"/api/v1/sellers/me/returns/{pk(req.id)}/accept",
            json={"otp": "999999", "restock": False},
        )
    locked = await client.post(
        f"/api/v1/sellers/me/returns/{pk(req.id)}/accept",
        json={"otp": "111222", "restock": False},
    )
    assert locked.status_code == 409
    assert locked.json()["detail"]["code"] == "receipt_otp_locked"

    # The customer reissues; the seller can try again with the new code.
    as_customer(seed.customer_user)
    resp = await client.post(f"/api/v1/returns/{pk(req.id)}/receipt-otp/resend")
    assert resp.status_code == 200, resp.text
    fresh = resp.json()["receipt_otp"]
    assert fresh is not None and fresh != "111222"

    as_seller(seed.seller_user)
    accepted = await client.post(
        f"/api/v1/sellers/me/returns/{pk(req.id)}/accept",
        json={"otp": fresh, "restock": False},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "closed"


async def test_receipt_code_resend_is_cooldown_limited(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _return(session, seed, status=ReturnStatus.active)
    row = await session.get(ReturnRequest, pk(req.id))
    assert row is not None
    row.receipt_otp_sent_at = datetime.now(timezone.utc)
    session.add(row)
    await session.commit()

    as_customer(seed.customer_user)
    resp = await client.post(f"/api/v1/returns/{pk(req.id)}/receipt-otp/resend")
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "resend_cooldown"
    assert resp.json()["detail"]["retry_after"] > 0


async def test_receipt_code_resend_only_while_active(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _return(
        session, seed, status=ReturnStatus.awaiting_customer_confirmation
    )
    as_customer(seed.customer_user)

    resp = await client.post(f"/api/v1/returns/{pk(req.id)}/receipt-otp/resend")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "return_not_active"


async def test_another_customer_cannot_reissue_the_code(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, email_suffix="owner")
    other = await seed_delivered_order(session, email_suffix="other")
    req = await _return(session, seed, status=ReturnStatus.active)
    as_customer(other.customer_user)

    resp = await client.post(f"/api/v1/returns/{pk(req.id)}/receipt-otp/resend")
    assert resp.status_code == 404


# ─── Finding: unlocked read-then-write on every transition ───────────────


async def test_lock_return_reads_the_row(session: AsyncSession) -> None:
    """`lock_return` is what every mutating path now goes through; if it stops
    returning the row, every transition silently 404s."""
    from app.services.returns import lock_return

    seed = await seed_delivered_order(session)
    req = await _return(session, seed, status=ReturnStatus.active)
    locked = await lock_return(session, pk(req.id))
    assert locked is not None
    assert locked.id == req.id
    assert await lock_return(session, 999999) is None


async def test_the_sweep_leaves_a_settled_return_alone(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Accept-then-sweep must not overwrite `closed` with `expired`, which
    would release lines the customer already got credit for."""
    from app.services.returns import expire_stale_returns

    seed = await seed_delivered_order(session)
    req = await _return(session, seed, status=ReturnStatus.active)
    as_seller(seed.seller_user)
    accepted = await client.post(
        f"/api/v1/sellers/me/returns/{pk(req.id)}/accept",
        json={"otp": "111222", "restock": False},
    )
    assert accepted.status_code == 200

    # Backdate the handover deadline so the sweep would pick it up if it
    # considered anything other than the live status.
    session.expunge_all()
    row = await session.get(ReturnRequest, pk(req.id))
    assert row is not None
    row.handover_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    session.add(row)
    await session.commit()

    assert await expire_stale_returns(session) == []
    await session.commit()
    session.expunge_all()
    final = await session.get(ReturnRequest, pk(req.id))
    assert final is not None
    assert final.status == ReturnStatus.closed
