# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Who hears about a return event, and what they are told."""
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.otp import hash_code
from app.core.redis import get_redis
from app.models.base import AccountStatus, User
from app.models.notification import Notification, NotificationType
from app.models.returns import (
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
)
from tests._returns_helpers import (
    SeededOrder,
    as_admin,
    as_customer,
    as_seller,
    clear_overrides,
    pk,
    seed_delivered_order,
)

REASON = "Customer brought the goods to the support desk"


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _return(
    session: AsyncSession,
    seed: SeededOrder,
    *,
    status: ReturnStatus = ReturnStatus.active,
    choice: ReturnSettlementChoice = ReturnSettlementChoice.store_credit,
    receipt_sent_ago: timedelta = timedelta(0),
) -> ReturnRequest:
    now = datetime.now(timezone.utc)
    parked = status == ReturnStatus.awaiting_payment_confirmation
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id, status=status,
        is_full_order=False, reason_code=ReturnReasonCode.damaged,
        items_amount=250.0, delivery_fee_amount=0.0, total_amount=250.0,
        settlement_choice=choice, agreement_policy_version=1,
        window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48),
        handover_expires_at=now + timedelta(days=7),
        receipt_otp=None if parked else "111222",
        receipt_otp_sent_at=None if parked else now - receipt_sent_ago,
        payment_amount=250.0 if parked else 0.0,
        decided_at=now if parked else None,
        payment_confirm_expires_at=now + timedelta(days=7) if parked else None,
    )
    session.add(req)
    await session.flush()
    session.add(ReturnRequestItem(
        return_request_id=req.id, order_item_id=seed.order_item_ids[0],
        quantity=1, product_name_snapshot="Ghee 1L", unit_price_snapshot=250.0,
        line_total=250.0,
    ))
    await session.commit()
    await session.refresh(req)
    return req


async def _rows(session: AsyncSession) -> tuple[list[Notification], list[Notification]]:
    rows = list((await session.exec(select(Notification))).all())
    return (
        [n for n in rows if n.customer_profile_id is not None],
        [n for n in rows if n.seller_profile_id is not None],
    )


async def test_force_close_to_withdrawn_sends_withdrawn_copy(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    """Nothing was settled, so the customer must not read "return complete"."""
    seed = await seed_delivered_order(session)
    req = await _return(session, seed)
    as_admin(admin_user)

    resp = await client.post(
        f"/api/v1/admin/returns/{pk(req.id)}/close", json={"reason": REASON}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "withdrawn"
    customer, _ = await _rows(session)
    assert len(customer) == 1
    assert customer[0].status_value == "withdrawn"
    assert "withdrawn" in customer[0].title
    assert "complete" not in customer[0].body


async def test_receipt_code_resend_does_not_ping_the_seller(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _return(session, seed, receipt_sent_ago=timedelta(minutes=10))
    as_customer(seed.customer_user)

    resp = await client.post(f"/api/v1/returns/{pk(req.id)}/receipt-otp/resend")

    assert resp.status_code == 200, resp.text
    customer, seller = await _rows(session)
    assert seller == []
    assert [n.type for n in customer] == [NotificationType.ReturnReceiptOtp]


async def test_payment_confirmation_notifies_the_seller(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _return(
        session, seed, status=ReturnStatus.awaiting_payment_confirmation,
        choice=ReturnSettlementChoice.payment,
    )
    redis = await get_redis()
    await redis.hset(  # type: ignore[misc]
        f"otp:return_payment:code:{seed.customer_user_id}:{pk(req.id)}",
        mapping={"code_hash": hash_code("424242"), "attempts": "0"},
    )
    as_customer(seed.customer_user)

    resp = await client.post(
        f"/api/v1/returns/{pk(req.id)}/payment/confirm", json={"otp": "424242"}
    )

    assert resp.status_code == 200, resp.text
    _, seller = await _rows(session)
    assert len(seller) == 1
    assert seller[0].type == NotificationType.SellerReturnRequest
    assert seller[0].status_value == "closed"
    assert "₹250.00" in seller[0].body


@pytest.mark.parametrize(
    ("action", "body", "expected_status"),
    [
        ("accept", {"reason": REASON, "restock": False}, "closed"),
        ("reject", {"reason": REASON}, "rejected"),
        ("close", {"reason": REASON}, "withdrawn"),
    ],
)
async def test_admin_force_paths_notify_the_seller(
    session: AsyncSession,
    client: AsyncClient,
    admin_user: User,
    action: str,
    body: dict[str, Any],
    expected_status: str,
) -> None:
    seed = await seed_delivered_order(session)
    req = await _return(session, seed)
    as_admin(admin_user)

    resp = await client.post(f"/api/v1/admin/returns/{pk(req.id)}/{action}", json=body)

    assert resp.status_code == 200, resp.text
    _, seller = await _rows(session)
    assert len(seller) == 1
    assert seller[0].type == NotificationType.SellerReturnRequest
    assert seller[0].status_value == expected_status
    assert seller[0].title.startswith("An admin")
    assert REASON in seller[0].body


async def test_seller_row_survives_an_inactive_customer(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    """The customer's account status gates the customer's comms only."""
    seed = await seed_delivered_order(session)
    req = await _return(session, seed)
    owner = await session.get(User, seed.customer_user_id)
    assert owner is not None
    owner.account_status = AccountStatus.deleted
    session.add(owner)
    await session.commit()
    as_admin(admin_user)

    resp = await client.post(
        f"/api/v1/admin/returns/{pk(req.id)}/reject", json={"reason": REASON}
    )

    assert resp.status_code == 200, resp.text
    customer, seller = await _rows(session)
    assert customer == []
    assert len(seller) == 1


async def test_admin_force_paths_email_the_seller(
    session: AsyncSession,
    client: AsyncClient,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.returns as returns_api

    sent: list[tuple[int, str, str]] = []
    monkeypatch.setattr(
        returns_api, "dispatch_admin_order_action",
        lambda order_id, action, reason: sent.append((order_id, action, reason)),
    )
    seed = await seed_delivered_order(session)
    req = await _return(session, seed)
    as_admin(admin_user)

    resp = await client.post(
        f"/api/v1/admin/returns/{pk(req.id)}/accept",
        json={"reason": REASON, "restock": False},
    )

    assert resp.status_code == 200, resp.text
    assert sent == [(seed.order_id, "return.force_accept", f"Return #{pk(req.id)}: {REASON}")]


async def test_cash_acceptance_copy_names_the_deadline(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _return(session, seed, choice=ReturnSettlementChoice.payment)
    as_seller(seed.seller_user)

    resp = await client.post(
        f"/api/v1/sellers/me/returns/{pk(req.id)}/accept",
        json={"otp": "111222", "restock": False},
    )

    assert resp.status_code == 200, resp.text
    customer, _ = await _rows(session)
    assert len(customer) == 1
    assert customer[0].status_value == "awaiting_payment_confirmation"
    assert "₹250.00" in customer[0].body
    assert "closes automatically after 7 days" in customer[0].body
