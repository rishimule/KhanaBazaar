# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any
from unittest.mock import patch

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.email_render import render_email
from app.models.notification import Notification, NotificationType
from tests._courier_helpers import place_courier_order, seed_courier_world


async def test_placement_uses_courier_copy_for_both_sides(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    rows = (await session.exec(select(Notification).where(Notification.order_id == order["id"]))).all()
    customer = next(r for r in rows if r.customer_profile_id is not None)
    seller = next(r for r in rows if r.seller_profile_id is not None)
    assert "awaiting courier quote" in customer.title
    assert seller.type is NotificationType.SellerNewOrder
    assert seller.title == f"New courier order #{order['id']} · ₹200.00 + courier"
    assert "Send a courier quote" in seller.body


def _placed_order(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "order_id": 7, "service_name": "Sweets", "store_name": "Ravi Sweets",
        "line_items": [{"name": "Kaju Katli", "qty": 2, "unit_price": 100.0, "line_total": 200.0}],
        "order_total": 200.0, "subtotal": 200.0, "delivery_fee": 0.0, "delivery_eta": None,
        "preferred_delivery": None, "upi_vpa": None, "upi_payable": None, "courier": True,
    }
    base.update(overrides)
    return base


def test_customer_placed_email_has_no_payment_for_courier() -> None:
    payload = render_email(
        "order_placed_customer",
        {"orders": [_placed_order()], "grand_total": 200.0, "customer_first_name": "Asha"},
    )
    assert "Nothing to pay yet" in payload.html
    assert "by UPI" not in payload.html
    assert "Courier charge: to be quoted" in payload.text


def test_seller_placed_email_asks_for_a_quote() -> None:
    payload = render_email("order_placed_seller", {
        "order_id": 7, "service_name": "Sweets", "store_name": "Ravi Sweets",
        "items": [{"name": "Kaju Katli", "qty": 2, "unit_price": 100.0, "line_total": 200.0}],
        "order_total": 200.0, "subtotal": 200.0, "delivery_fee": 0.0,
        "preferred_delivery": None, "courier": True,
    })
    assert "send the customer a courier quote" in payload.html
    assert "Courier order" in payload.preheader


def test_status_email_says_shipped_with_tracking_and_refund() -> None:
    shipped = render_email("order_status_changed", {
        "order_id": 7, "service_name": "Sweets", "store_name": "Ravi Sweets",
        "current": "dispatched", "reason": None, "recipient": "customer",
        "mode": "courier", "status_label": "shipped",
        "tracking_line": "DTDC · D123", "refund_due_amount": None,
    })
    refund = render_email("order_status_changed", {
        "order_id": 7, "service_name": "Sweets", "store_name": "Ravi Sweets",
        "current": "cancelled", "reason": "No courier to your PIN", "recipient": "customer",
        "mode": "courier", "status_label": "cancelled",
        "tracking_line": None, "refund_due_amount": 320.0,
    })
    assert "is now shipped" in shipped.subject
    assert "DTDC · D123" in shipped.html
    # Courier pills (lowercase in the markup; CSS capitalizes them).
    assert ">requested</div>" in shipped.html and ">quote</div>" in shipped.html
    assert "Refund due" in refund.html


def test_status_email_still_renders_without_courier_keys() -> None:
    payload = render_email("order_status_changed", {
        "order_id": 7, "service_name": "Sweets", "store_name": "Ravi Sweets",
        "current": "packed", "reason": None, "recipient": "customer",
    })
    assert "is now packed" in payload.subject


def test_status_worker_passes_courier_keys() -> None:
    from app import worker

    ctx = {
        "order_id": 7, "service_name": "Sweets", "store_name": "Ravi Sweets",
        "customer_email": "c@kb.test", "customer_lang": "en", "customer_account_status": "active",
        "delivery_mode": "courier", "payment_status": "paid", "payment_amount": 320.0,
        "courier_carrier": "DTDC", "courier_tracking_number": "D123", "courier_tracking_url": None,
    }
    captured: dict[str, Any] = {}

    def _capture(to: str, subject: str, body: str, *, html: str | None = None, reply_to: str | None = None) -> None:
        captured.update(subject=subject, html=html or "")

    with (
        patch("app.worker._load_order_email_context", return_value=ctx),
        patch("app.worker._resolve_email", side_effect=_capture),
    ):
        worker.send_order_status_changed_async(7, "dispatched", "customer")
    assert "is now shipped" in captured["subject"]
    assert "DTDC · D123" in captured["html"]


def test_status_whatsapp_uses_courier_templates() -> None:
    from app import worker

    sent: list[str] = []

    class _Sender:
        async def send_template(self, to: str, template: Any, variables: dict[str, str]) -> None:
            sent.append(template.name)

    ctx = {
        "store_name": "Ravi Sweets", "customer_phone": "+919900000001",
        "customer_phone_verified": True, "delivery_mode": "courier",
    }
    with (
        patch("app.core.whatsapp.get_whatsapp_sender", lambda: _Sender()),
        patch("app.worker._load_order_email_context", return_value=ctx),
    ):
        worker.send_order_status_whatsapp_async(7, "dispatched")
        worker.send_order_status_whatsapp_async(7, "pending")
    assert sent == ["courier_shipped"]


def test_status_email_tells_the_seller_they_owe_the_refund() -> None:
    # The seller's own copy of the cancellation must not say their store owes
    # them money.
    payload = render_email("order_status_changed", {
        "order_id": 7, "service_name": "Sweets", "store_name": "Ravi Sweets",
        "current": "cancelled", "reason": "No courier to your PIN", "recipient": "seller",
        "mode": "courier", "status_label": "cancelled",
        "tracking_line": None, "refund_due_amount": 320.0,
    })
    assert "You owe the customer a refund of" in payload.html
    assert "You owe the customer a refund of" in payload.text
    assert "Refund due" not in payload.html and "Refund due" not in payload.text
