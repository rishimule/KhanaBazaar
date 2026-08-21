# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.returns import (
    CustomerStoreCredit,
    ReturnEvent,
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
)
from app.models.store import StoreInventory
from tests._returns_helpers import (
    as_seller,
    clear_overrides,
    publish_return_agreement,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _active_return(
    session: AsyncSession,
    seed: Any,
    *,
    choice: ReturnSettlementChoice = ReturnSettlementChoice.store_credit,
    code: str = "111222",
    item_index: int = 0,
) -> ReturnRequest:
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id, status=ReturnStatus.active,
        is_full_order=False, reason_code=ReturnReasonCode.damaged,
        items_amount=250.0, delivery_fee_amount=0.0, total_amount=250.0,
        settlement_choice=choice, agreement_policy_version=1,
        window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48),
        handover_expires_at=now + timedelta(days=7),
        receipt_otp=code, receipt_otp_sent_at=now,
    )
    session.add(req)
    await session.flush()
    session.add(ReturnRequestItem(
        return_request_id=req.id, order_item_id=seed.order_item_ids[item_index],
        quantity=1, product_name_snapshot="Ghee 1L", unit_price_snapshot=250.0,
        line_total=250.0,
    ))
    await session.commit()
    await session.refresh(req)
    return req


async def test_correct_code_accepts_and_credits(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    resp = await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/accept",
        json={"otp": "111222", "restock": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "closed"
    assert body["store_credit_amount"] == 250.0

    acct = (await session.exec(select(CustomerStoreCredit))).first()
    assert acct is not None
    assert acct.balance == 250.0

    session.expunge_all()
    row = await session.get(ReturnRequest, req.id)
    assert row is not None
    assert row.receipt_otp is None
    assert row.receipt_otp_verified_at is not None
    assert row.decided_at is not None


async def test_payment_choice_parks_after_acceptance(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed, choice=ReturnSettlementChoice.payment)
    as_seller(seed.seller_user)

    body = (await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/accept",
        json={"otp": "111222", "restock": False},
    )).json()
    assert body["status"] == "awaiting_payment_confirmation"
    assert body["payment_amount"] == 250.0


async def test_wrong_code_counts_an_attempt_and_does_not_accept(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    resp = await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/accept",
        json={"otp": "999999", "restock": False},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "receipt_otp_invalid"
    assert resp.json()["detail"]["remaining"] == 4

    session.expunge_all()
    row = await session.get(ReturnRequest, req.id)
    assert row is not None
    assert row.status == ReturnStatus.active
    assert row.receipt_otp_attempts == 1


async def test_non_ascii_code_is_a_failed_attempt_not_a_crash(
    session: AsyncSession, client: AsyncClient
) -> None:
    """compare_digest raises TypeError on non-ASCII; isascii() must short-circuit."""
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    resp = await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/accept",
        json={"otp": "११२२३३", "restock": False},
    )
    assert resp.status_code == 422
    session.expunge_all()
    row = await session.get(ReturnRequest, req.id)
    assert row is not None
    assert row.receipt_otp_attempts == 1


async def test_missing_code_is_refused(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    resp = await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/accept", json={"restock": False}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "receipt_otp_required"


async def test_lockout_after_max_attempts(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    for _ in range(5):
        await client.post(
            f"/api/v1/sellers/me/returns/{req.id}/accept",
            json={"otp": "999999", "restock": False},
        )
    resp = await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/accept",
        json={"otp": "111222", "restock": False},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "receipt_otp_locked"


async def test_restock_returns_stock_when_asked(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, with_inventory=True)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/accept",
        json={"otp": "111222", "restock": True},
    )
    session.expunge_all()
    inv = await session.get(StoreInventory, seed.inventory_ids[0])
    assert inv is not None
    assert inv.stock == 11


async def test_restock_defaults_to_leaving_stock_alone(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Returned groceries are often unsellable — phantom stock oversells."""
    seed = await seed_delivered_order(session, with_inventory=True)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/accept",
        json={"otp": "111222", "restock": False},
    )
    session.expunge_all()
    inv = await session.get(StoreInventory, seed.inventory_ids[0])
    assert inv is not None
    assert inv.stock == 10


async def test_restock_skips_delisted_lines(
    session: AsyncSession, client: AsyncClient
) -> None:
    """An order line whose product was de-listed has inventory_id NULL."""
    seed = await seed_delivered_order(session, with_inventory=False)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    resp = await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/accept",
        json={"otp": "111222", "restock": True},
    )
    assert resp.status_code == 200


async def test_rejection_records_the_reason_and_releases_lines(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    resp = await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/reject",
        json={"reason": "Seal broken and contents partly used"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert resp.json()["rejection_reason"] == "Seal broken and contents partly used"

    events = (await session.exec(
        select(ReturnEvent).where(ReturnEvent.return_request_id == req.id)
    )).all()
    assert events[-1].to_status == ReturnStatus.rejected
    assert events[-1].actor_role == "seller"


async def test_rejection_requires_a_reason(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    resp = await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/reject", json={"reason": "  "}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "reason_required"


async def test_accepting_a_terminal_return_is_refused(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)
    await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/reject", json={"reason": "not sellable"}
    )

    resp = await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/accept",
        json={"otp": "111222", "restock": False},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "illegal_return_transition"


async def test_seller_can_initiate_on_a_customers_behalf(
    session: AsyncSession, client: AsyncClient
) -> None:
    """BRD scope: a seller may start a return, but it is inert until the
    customer accepts the agreement and confirms by OTP."""
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_seller(seed.seller_user)

    resp = await client.post(
        "/api/v1/sellers/me/returns",
        json={
            "order_id": seed.order_id,
            "order_item_ids": [seed.order_item_ids[0]],
            "reason_code": "damaged",
            "settlement_choice": "store_credit",
            "customer_profile_id": seed.customer_profile_id,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "awaiting_customer_confirmation"
    assert body["initiated_by"] == "seller"


async def test_seller_cannot_initiate_for_another_sellers_order(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, email_suffix="owner")
    intruder = await seed_delivered_order(session, email_suffix="other")
    await publish_return_agreement(session)
    as_seller(intruder.seller_user)

    resp = await client.post(
        "/api/v1/sellers/me/returns",
        json={
            "order_id": seed.order_id,
            "order_item_ids": [seed.order_item_ids[0]],
            "reason_code": "damaged",
            "settlement_choice": "store_credit",
            "customer_profile_id": seed.customer_profile_id,
        },
    )
    assert resp.status_code == 404


async def test_another_seller_cannot_decide(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, email_suffix="owner")
    intruder = await seed_delivered_order(session, email_suffix="other")
    req = await _active_return(session, seed)
    as_seller(intruder.seller_user)

    resp = await client.post(
        f"/api/v1/sellers/me/returns/{req.id}/accept",
        json={"otp": "111222", "restock": False},
    )
    assert resp.status_code == 404
