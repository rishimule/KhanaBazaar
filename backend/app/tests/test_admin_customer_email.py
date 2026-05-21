# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Tests for the admin-action → customer notification fanout."""

from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    "action,should_notify_customer",
    [
        ("order.rewind", True),
        ("order.refund", True),
        ("order.cancel", True),
        ("order.address_override", True),
        ("order.transition", False),
    ],
)
def test_dispatch_routes_customer_notification_only_for_impactful_actions(
    monkeypatch: pytest.MonkeyPatch, action: str, should_notify_customer: bool
) -> None:
    seller_calls: list[tuple] = []
    customer_calls: list[tuple] = []

    from app.worker import (
        send_admin_order_action_customer_async,
        send_admin_order_action_seller_async,
    )

    monkeypatch.setattr(
        send_admin_order_action_seller_async,
        "delay",
        lambda *a, **k: seller_calls.append(a),
    )
    monkeypatch.setattr(
        send_admin_order_action_customer_async,
        "delay",
        lambda *a, **k: customer_calls.append(a),
    )

    from app.services.order_emails import dispatch_admin_order_action

    dispatch_admin_order_action(123, action, "reason text")

    assert len(seller_calls) == 1
    assert (len(customer_calls) == 1) == should_notify_customer


def test_admin_order_action_customer_renders_address_override_template() -> None:
    from app import worker

    captured: dict[str, str] = {}

    def _capture(to, subject, body, *, html=None, reply_to=None):
        captured["to"] = to
        captured["subject"] = subject
        captured["html"] = html or ""

    fake_ctx = {
        "order_id": 7,
        "order_total": 100.0,
        "order_status": "pending",
        "service_name": "Grocery",
        "store_name": "Test Store",
        "seller_email": "seller@example.com",
        "customer_email": "customer@example.com",
        "items": [],
        "customer_first_name": "Ravi",
        "customer_lang": "en",
        "seller_lang": "en",
        "delivery_address_snapshot": "42 New Street, Mumbai 400001",
    }

    with (
        patch("app.worker._load_order_email_context", return_value=fake_ctx),
        patch("app.worker._resolve_email", side_effect=_capture),
    ):
        worker.send_admin_order_action_customer_async(
            7, "order.address_override", "moved house"
        )

    assert captured["to"] == "customer@example.com"
    assert "Delivery address updated" in captured["html"]
    assert "42 New Street, Mumbai 400001" in captured["html"]
    assert "moved house" in captured["html"]
    assert "/account/orders/7" in captured["html"]
