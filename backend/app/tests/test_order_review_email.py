# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Tests for the post-delivery order review-request email."""

from unittest.mock import patch

import pytest


def test_delivered_status_schedules_review_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    from app.worker import (
        send_order_review_request_async,
        send_order_status_changed_async,
    )

    def fake_apply_async(*args, **kwargs):
        captured["args"] = kwargs.get("args") or args
        captured["countdown"] = kwargs.get("countdown")

    monkeypatch.setattr(
        send_order_review_request_async, "apply_async", fake_apply_async
    )
    monkeypatch.setattr(
        send_order_status_changed_async, "delay", lambda *a, **k: None
    )

    from app.services.order_emails import dispatch_order_status_changed

    dispatch_order_status_changed(42, "delivered", notify_seller=False)

    assert captured["countdown"] == 86400
    args = captured["args"]
    if isinstance(args, dict):
        assert args.get("args") == [42]
    else:
        assert args == [42] or args == (42,)


def test_non_delivered_status_does_not_schedule_review(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    from app.worker import (
        send_order_review_request_async,
        send_order_status_changed_async,
    )

    monkeypatch.setattr(
        send_order_review_request_async,
        "apply_async",
        lambda *a, **k: seen.append(1),
    )
    monkeypatch.setattr(
        send_order_status_changed_async, "delay", lambda *a, **k: None
    )

    from app.services.order_emails import dispatch_order_status_changed

    dispatch_order_status_changed(42, "packed")
    assert seen == []


def test_order_review_request_renders_cta_to_order_detail_page() -> None:
    from app import worker

    captured: dict[str, str] = {}

    def _capture(to, subject, body, *, html=None, reply_to=None):
        captured["to"] = to
        captured["subject"] = subject
        captured["html"] = html or ""

    fake_ctx = {
        "order_id": 11,
        "order_total": 100.0,
        "order_status": "delivered",
        "service_name": "Grocery",
        "store_name": "Test Store",
        "seller_email": "seller@example.com",
        "customer_email": "customer@example.com",
        "items": [],
        "customer_first_name": "Ravi",
        "customer_lang": "en",
        "seller_lang": "en",
        "delivery_address_snapshot": "",
    }

    with (
        patch("app.worker._load_order_email_context", return_value=fake_ctx),
        patch("app.worker._resolve_email", side_effect=_capture),
    ):
        worker.send_order_review_request_async(11)

    assert captured["to"] == "customer@example.com"
    assert "#11" in captured["subject"]
    assert "/account/orders/11" in captured["html"]
    assert "Rate your order" in captured["html"]
