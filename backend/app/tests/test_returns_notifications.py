# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
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
    as_customer,
    as_seller,
    clear_overrides,
    pk,
    publish_return_agreement,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _active_return(session: AsyncSession, seed: Any) -> ReturnRequest:
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id, status=ReturnStatus.active,
        is_full_order=False, reason_code=ReturnReasonCode.damaged,
        items_amount=250.0, delivery_fee_amount=0.0, total_amount=250.0,
        settlement_choice=ReturnSettlementChoice.store_credit,
        agreement_policy_version=1, window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48),
        handover_expires_at=now + timedelta(days=7),
        receipt_otp="111222", receipt_otp_sent_at=now,
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


async def _notifications(session: AsyncSession) -> list[Notification]:
    return list((await session.exec(select(Notification))).all())


async def test_confirming_notifies_the_customer_and_the_seller(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = (await client.post("/api/v1/returns", json={
        "order_id": seed.order_id, "order_item_ids": seed.order_item_ids,
        "reason_code": "damaged", "settlement_choice": "store_credit",
    })).json()["id"]

    redis = await get_redis()
    await redis.hset(  # type: ignore[misc]
        f"otp:return_initiate:code:{seed.customer_user_id}:{rid}",
        mapping={"code_hash": hash_code("424242"), "attempts": "0"},
    )
    resp = await client.post(
        f"/api/v1/returns/{rid}/confirm",
        json={"otp": "424242", "agreement_accepted": True},
    )
    code = resp.json()["receipt_otp"]

    rows = await _notifications(session)
    customer_rows = [n for n in rows if n.customer_profile_id is not None]
    seller_rows = [n for n in rows if n.seller_profile_id is not None]

    receipt = [n for n in customer_rows if n.type == NotificationType.ReturnReceiptOtp]
    assert len(receipt) == 1
    assert code in receipt[0].body
    assert receipt[0].return_request_id == rid

    assert len(seller_rows) == 1
    assert seller_rows[0].type == NotificationType.SellerReturnRequest
    assert seller_rows[0].return_request_id == rid


async def test_creation_notifies_the_customer(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    await client.post("/api/v1/returns", json={
        "order_id": seed.order_id, "order_item_ids": seed.order_item_ids,
        "reason_code": "damaged", "settlement_choice": "store_credit",
    })

    rows = await _notifications(session)
    assert len(rows) == 1
    assert rows[0].type == NotificationType.ReturnStatusUpdate
    assert rows[0].status_value == "awaiting_customer_confirmation"


async def test_seller_rejection_notifies_the_customer_with_the_reason(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    await client.post(
        f"/api/v1/sellers/me/returns/{pk(req.id)}/reject",
        json={"reason": "Seal broken and contents partly used"},
    )
    rows = [n for n in await _notifications(session) if n.customer_profile_id]
    assert len(rows) == 1
    assert rows[0].status_value == "rejected"
    assert "Seal broken" in rows[0].body


async def test_acceptance_notifies_the_customer(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    await client.post(
        f"/api/v1/sellers/me/returns/{pk(req.id)}/accept",
        json={"otp": "111222", "restock": False},
    )
    rows = [n for n in await _notifications(session) if n.customer_profile_id]
    assert len(rows) == 1
    assert rows[0].status_value == "closed"
    assert rows[0].type == NotificationType.ReturnStatusUpdate


async def test_notifications_are_skipped_for_a_non_active_account(
    session: AsyncSession, client: AsyncClient
) -> None:
    """An admin-deleted customer with a live return gets no in-app row."""
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    owner = await session.get(User, seed.customer_user_id)
    assert owner is not None
    owner.account_status = AccountStatus.deleted
    session.add(owner)
    await session.commit()
    as_seller(seed.seller_user)

    await client.post(
        f"/api/v1/sellers/me/returns/{pk(req.id)}/reject",
        json={"reason": "customer account was removed"},
    )
    assert [n for n in await _notifications(session) if n.customer_profile_id] == []


async def test_notification_failure_never_breaks_the_return(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A comms outage must not fail a return that already committed."""
    import app.api.returns as returns_api

    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)

    async def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("notification backend down")

    monkeypatch.setattr(returns_api, "record_return_notification", _boom)
    as_seller(seed.seller_user)

    resp = await client.post(
        f"/api/v1/sellers/me/returns/{pk(req.id)}/reject",
        json={"reason": "still rejected despite comms failure"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


async def test_expiry_sweep_writes_a_notification(session: AsyncSession) -> None:
    from app.services.returns import expire_stale_returns

    seed = await seed_delivered_order(session)
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id,
        status=ReturnStatus.awaiting_customer_confirmation, is_full_order=False,
        reason_code=ReturnReasonCode.damaged, items_amount=10.0,
        delivery_fee_amount=0.0, total_amount=10.0,
        settlement_choice=ReturnSettlementChoice.store_credit,
        agreement_policy_version=1, window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now - timedelta(hours=1),
    )
    session.add(req)
    await session.commit()

    await expire_stale_returns(session)
    await session.commit()

    rows = await _notifications(session)
    assert len(rows) == 1
    assert rows[0].status_value == "expired"


def test_every_return_email_template_renders() -> None:
    """The dispatchers are patched out in tests, so without this a broken
    template would only surface in production."""
    from app.core.email_render import render_email

    ctx: dict[str, Any] = {
        "return_id": 7, "order_id": 3, "store_name": "Anil Stores",
        "service_name": "Grocery", "total_amount": "870.00", "currency": "INR ",
        "confirm_hours": 48, "receipt_code": "483920",
        "rejection_reason": "Seal broken", "customer_first_name": "Riya",
        "settlement_line": "870.00 was added as store credit.",
    }
    for event in (
        "return_initiated", "return_confirmed", "return_accepted",
        "return_rejected", "return_closed", "return_expired",
    ):
        payload = render_email(event, ctx, lang="en")
        assert payload.subject and payload.html and payload.text, event
        assert "{{" not in payload.html, f"unrendered placeholder in {event}"


def test_every_return_whatsapp_template_renders() -> None:
    from app.core.whatsapp_templates import TEMPLATES

    cases = {
        "otp_return": {"return_no": "7", "code": "483920"},
        "return_initiated": {"return_no": "7", "store": "Anil Stores"},
        "return_confirmed": {"return_no": "7", "code": "483920"},
        "return_accepted": {"return_no": "7", "amount": "870.00"},
        "return_rejected": {"return_no": "7", "reason": "Seal broken"},
        "return_closed": {"return_no": "7", "amount": "870.00"},
    }
    for name, variables in cases.items():
        template = TEMPLATES[name]
        assert set(template.variables) == set(variables), name
        assert template.render(variables), name


def test_settlement_line_covers_every_split() -> None:
    from app.worker import _settlement_line

    reversal_only = _settlement_line(
        {"credit_reversal_amount": 100.0, "store_credit_amount": 0.0, "payment_amount": 0.0}
    )
    assert "owe this store" in reversal_only

    split = _settlement_line(
        {"credit_reversal_amount": 120.0, "store_credit_amount": 380.0, "payment_amount": 0.0}
    )
    assert "owe this store" in split and "store credit" in split

    nothing = _settlement_line(
        {"credit_reversal_amount": 0.0, "store_credit_amount": 0.0, "payment_amount": 0.0}
    )
    assert "No amount was outstanding" in nothing
