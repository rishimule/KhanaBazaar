# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import AccountStatus, User
from app.models.commerce import Order, OrderStatus
from app.models.notification import Notification, NotificationType
from app.models.profile import CustomerProfile, SellerProfile, VerificationStatus
from app.services import courier_comms
from app.services.courier_copy import (
    CUSTOMER_EVENTS,
    SELLER_EVENTS,
    CourierVars,
    load_courier_vars,
    render_customer,
    render_seller,
    render_status,
)
from tests._courier_helpers import CUSTOMER, insert_courier_order, seed_courier_world


def _vars(**overrides: Any) -> CourierVars:
    base: dict[str, Any] = {
        "order_id": 42, "status": "quoted", "store_name": "Ravi Sweets",
        "customer_profile_id": 1, "customer_active": True,
        "customer_email": "c@kb.test", "customer_phone": "+919900000001",
        "customer_phone_verified": True, "seller_profile_id": 2,
        "seller_active": True, "seller_email": "s@kb.test", "total": 320.0,
        "payable": 320.0, "payment_method": "upi", "payment_status": "pending",
        "fee": 120.0, "min_days": 3, "max_days": 5,
        "eta_from": date(2026, 10, 5), "eta_to": date(2026, 10, 7),
        "carrier_name": "DTDC", "tracking_number": "D123", "claim_note": None,
        "cancel_reason": None, "refund_reference": None,
    }
    base.update(overrides)
    return CourierVars(**base)


@pytest.mark.parametrize("event", sorted(CUSTOMER_EVENTS))
def test_every_customer_event_has_copy(event: str) -> None:
    message = render_customer(event, _vars())
    assert message.title and message.body
    assert "#42" in message.title + message.body


@pytest.mark.parametrize("event", sorted(SELLER_EVENTS))
def test_every_seller_event_has_copy(event: str) -> None:
    message = render_seller(event, _vars())
    assert message.title and message.body
    assert "#42" in message.title


def test_quote_copy_carries_amount_and_transit() -> None:
    message = render_customer("quote_ready", _vars())
    assert "₹120.00" in message.body and "3–5 days" in message.body


def test_status_copy_for_courier_orders() -> None:
    pending = render_status("pending", _vars(status="pending"))
    shipped = render_status("dispatched", _vars(status="dispatched"))
    refund = render_status("cancelled", _vars(status="cancelled", payment_status="paid"))
    assert pending is not None and "awaiting courier quote" in pending.title
    assert shipped is not None and "DTDC · D123" in shipped.body and "5 Oct" in shipped.body
    assert refund is not None and "refund of ₹320.00" in refund.body
    assert render_status("quoted", _vars()) is None


async def test_load_courier_vars_reads_the_rows(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world, status=OrderStatus.Quoted, quote_fee=120.0)
    v = await load_courier_vars(session, order_id)
    assert v is not None
    assert (v.store_name, v.fee, v.min_days, v.max_days) == ("Ravi Sweets", 120.0, 3, 5)
    assert v.customer_active and v.seller_active
    assert v.customer_email == CUSTOMER.email


async def test_customer_event_records_row_and_fans_out(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world, status=OrderStatus.Quoted, quote_fee=120.0)
    order = await session.get(Order, order_id)
    assert order is not None
    email, whatsapp, push = MagicMock(), MagicMock(), MagicMock()
    with (
        patch.object(courier_comms, "dispatch_courier_email", email),
        patch.object(courier_comms, "dispatch_courier_whatsapp", whatsapp),
        patch.object(courier_comms, "dispatch_notification_push", push),
    ):
        await courier_comms.notify_customer(session, order, "quote_ready")
    row = (await session.exec(select(Notification).where(Notification.order_id == order_id))).one()
    assert row.customer_profile_id == world.customer_profile_id
    assert row.status_value == "courier_quote_ready"
    assert "₹120.00" in row.body
    email.assert_called_once_with(order_id, "quote_ready", "customer")
    whatsapp.assert_called_once_with(order_id, "quote_ready")
    push.assert_called_once_with(row.id)
    assert order.id == order_id  # refreshed, still readable


async def test_tracking_update_skips_email(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world, status=OrderStatus.Dispatched)
    order = await session.get(Order, order_id)
    assert order is not None
    email = MagicMock()
    with patch.object(courier_comms, "dispatch_courier_email", email):
        await courier_comms.notify_customer(session, order, "tracking_updated")
    email.assert_not_called()


async def test_inactive_customer_gets_nothing(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world, quote_fee=120.0)
    profile = await session.get(CustomerProfile, world.customer_profile_id)
    assert profile is not None
    user = await session.get(User, profile.user_id)
    assert user is not None
    user.account_status = AccountStatus.suspended
    user.is_active = False
    await session.commit()
    order = await session.get(Order, order_id)
    assert order is not None
    await courier_comms.notify_customer(session, order, "quote_ready")
    rows = (await session.exec(select(Notification).where(Notification.order_id == order_id))).all()
    assert rows == []


async def test_seller_event_records_seller_row(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world, status=OrderStatus.Accepted, claimed=True)
    order = await session.get(Order, order_id)
    assert order is not None
    email = MagicMock()
    with patch.object(courier_comms, "dispatch_courier_email", email):
        await courier_comms.notify_seller(session, order, "payment_claimed")
    row = (await session.exec(select(Notification).where(Notification.order_id == order_id))).one()
    assert row.seller_profile_id == world.seller_profile_id
    assert row.type is NotificationType.SellerOrderUpdate
    assert row.status_value == "courier_payment_claimed"
    email.assert_called_once_with(order_id, "payment_claimed", "seller")


async def test_once_skips_a_repeat(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world, status=OrderStatus.Quoted, quote_fee=120.0)
    order = await session.get(Order, order_id)
    assert order is not None
    await courier_comms.notify_seller(session, order, "payee_missing", once=True)
    await courier_comms.notify_seller(session, order, "payee_missing", once=True)
    rows = (await session.exec(select(Notification).where(Notification.order_id == order_id))).all()
    assert len(rows) == 1


async def test_a_rejected_seller_is_not_told_to_add_a_payee(session: AsyncSession) -> None:
    """Rejection, not missing details, is why their customers can't pay, so
    "add a UPI ID" would be advice they can't act on; other events still go."""
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world, status=OrderStatus.Quoted, quote_fee=120.0)
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    seller.verification_status = VerificationStatus.Rejected
    session.add(seller)
    await session.commit()
    order = await session.get(Order, order_id)
    assert order is not None
    await courier_comms.notify_seller(session, order, "payee_missing", once=True)
    await courier_comms.notify_seller(session, order, "customer_cancelled")
    rows = (await session.exec(select(Notification).where(Notification.order_id == order_id))).all()
    assert [r.status_value for r in rows] == ["courier_customer_cancelled"]


async def test_courier_email_renders_template(session: AsyncSession) -> None:
    from app import worker

    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world, status=OrderStatus.Quoted, quote_fee=120.0)
    captured: dict[str, Any] = {}

    def _capture(to: str, subject: str, body: str, *, html: str | None = None, reply_to: str | None = None) -> None:
        captured.update(to=to, subject=subject, body=body, html=html or "")

    with patch("app.worker._resolve_email", side_effect=_capture):
        await worker.courier_email(order_id, "quote_ready", "customer")
    assert captured["to"] == CUSTOMER.email
    assert f"Courier quote for order #{order_id}" in captured["subject"]
    assert f"/account/orders/{order_id}" in captured["html"]
    assert "₹120.00" in captured["body"]


async def test_courier_whatsapp_uses_the_quote_template(session: AsyncSession) -> None:
    from app import worker

    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world, status=OrderStatus.Quoted, quote_fee=120.0)
    profile = await session.get(CustomerProfile, world.customer_profile_id)
    assert profile is not None
    profile.phone_verified_at = datetime.now(timezone.utc)
    await session.commit()
    sent: list[tuple[str, str, dict[str, str]]] = []

    class _Sender:
        async def send_template(self, to: str, template: Any, variables: dict[str, str]) -> None:
            sent.append((to, template.name, variables))

    with patch("app.core.whatsapp.get_whatsapp_sender", lambda: _Sender()):
        await worker.courier_whatsapp(order_id, "quote_ready")
    assert sent == [("+919900000001", "courier_quote_ready", {
        "order_no": str(order_id), "store": "Ravi Sweets", "amount": "120.00", "days": "3–5",
    })]
