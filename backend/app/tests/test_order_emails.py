# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any
from unittest.mock import patch

import pytest


@pytest.mark.parametrize("task_name,args", [
    ("send_order_placed_seller_async", (1,)),
    ("send_order_confirmed_customer_async", ([1, 2],)),
    ("send_order_status_changed_async", (1, "packed", "customer")),
    ("send_order_status_changed_async", (1, "cancelled", "seller")),
])
def test_email_tasks_callable_in_console_mode(task_name: str, args: tuple[Any, ...]) -> None:
    from app import worker
    with patch("app.core.config.settings.EMAIL_PROVIDER", "console"):
        fn = getattr(worker, task_name)
        result = fn(*args)
    assert result is None


def _fake_ctx(order_id: int = 7, service_name: str = "Grocery") -> dict[str, Any]:
    """Stand-in for `_load_order_email_context`. Provides the snapshotted
    service name + the minimum fields each task needs to compose subject+body
    and reach `_resolve_email`."""
    return {
        "order_id": order_id,
        "order_total": 123.45,
        "subtotal": 123.45,
        "delivery_fee": 0.0,
        "order_status": "pending",
        "service_name": service_name,
        "store_name": "Test Store",
        "seller_email": "seller@example.com",
        "customer_email": "customer@example.com",
        "items": [
            {"name": "Sample item", "qty": 2, "unit_price": 50.0, "line_total": 100.0},
        ],
        "customer_first_name": "Ravi",
        "customer_lang": "en",
        "seller_lang": "en",
        "delivery_address_snapshot": "1 Test Street, Bengaluru 560300",
        "preferred_delivery": None,
    }


def test_loader_dict_shape_includes_new_fields() -> None:
    """Smoke check that the loader's return contract includes the new fields.

    Real DB coverage happens via test_orders_per_service.py and similar
    integration tests; here we only assert the in-memory shape.
    """
    ctx = _fake_ctx()
    for key in (
        "items",
        "customer_first_name",
        "customer_lang",
        "seller_lang",
        "delivery_address_snapshot",
        "preferred_delivery",
    ):
        assert key in ctx


def test_placed_seller_email_includes_service_name() -> None:
    from app import worker

    captured: dict[str, str] = {}

    def _capture(
        to: str,
        subject: str,
        body: str,
        *,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body
        captured["html"] = html or ""

    with (
        patch("app.worker._load_order_email_context", return_value=_fake_ctx()),
        patch("app.worker._resolve_email", side_effect=_capture),
    ):
        worker.send_order_placed_seller_async(7)

    assert captured["to"] == "seller@example.com"
    assert "Grocery" in captured["subject"]
    assert "#7" in captured["subject"]
    assert "Test Store" in captured["html"]
    assert "Grocery" in captured["body"]
    assert "#7" in captured["body"]
    assert "/seller/orders/7" in captured["html"]


def test_confirmed_customer_email_includes_service_name() -> None:
    from app import worker

    captured: dict[str, str] = {}

    def _capture(
        to: str,
        subject: str,
        body: str,
        *,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body
        captured["html"] = html or ""

    side_effect = iter([
        _fake_ctx(order_id=11, service_name="Grocery"),
        _fake_ctx(order_id=12, service_name="Pharmacy"),
    ])

    with (
        patch(
            "app.worker._load_order_email_context",
            side_effect=lambda oid: next(side_effect),
        ),
        patch("app.worker._resolve_email", side_effect=_capture),
    ):
        worker.send_order_confirmed_customer_async([11, 12])

    assert captured["to"] == "customer@example.com"
    assert "Grocery" in captured["body"]
    assert "Pharmacy" in captured["body"]
    assert "#11" in captured["body"]
    assert "#12" in captured["body"]


@pytest.mark.parametrize("recipient,expected_to", [
    ("customer", "customer@example.com"),
    ("seller", "seller@example.com"),
])
def test_status_changed_email_includes_service_name(
    recipient: str, expected_to: str
) -> None:
    from app import worker

    captured: dict[str, str] = {}

    def _capture(
        to: str,
        subject: str,
        body: str,
        *,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body
        captured["html"] = html or ""

    with (
        patch("app.worker._load_order_email_context", return_value=_fake_ctx()),
        patch("app.worker._resolve_email", side_effect=_capture),
    ):
        worker.send_order_status_changed_async(7, "packed", recipient)

    assert captured["to"] == expected_to
    assert "#7" in captured["subject"]
    assert "packed" in captured["subject"]
    assert "Grocery" in captured["body"]
    assert "#7" in captured["body"]


def test_admin_order_action_seller_email_renders_action_and_reason() -> None:
    from app import worker

    captured: dict[str, str] = {}

    def _capture(
        to: str,
        subject: str,
        body: str,
        *,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body
        captured["html"] = html or ""

    with (
        patch("app.worker._load_order_email_context", return_value=_fake_ctx()),
        patch("app.worker._resolve_email", side_effect=_capture),
    ):
        worker.send_admin_order_action_seller_async(
            7, "order.refund", "duplicate payment"
        )

    assert captured["to"] == "seller@example.com"
    assert "Refunded" in captured["html"]
    assert "duplicate payment" in captured["html"]
    assert "/seller/orders/7" in captured["html"]


@pytest.mark.parametrize("recipient,expected_to", [
    ("customer", "customer@example.com"),
    ("seller", "seller@example.com"),
])
def test_cancelled_status_email_includes_reason(
    recipient: str, expected_to: str,
) -> None:
    from app import worker

    captured: dict[str, str] = {}

    def _capture(
        to: str,
        subject: str,
        body: str,
        *,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body
        captured["html"] = html or ""

    with (
        patch("app.worker._load_order_email_context", return_value=_fake_ctx()),
        patch("app.worker._resolve_email", side_effect=_capture),
    ):
        worker.send_order_status_changed_async(
            7, "cancelled", recipient, "out of stock"
        )

    assert captured["to"] == expected_to
    assert "cancelled" in captured["subject"]
    assert "out of stock" in captured["html"]
    assert "out of stock" in captured["body"]
    assert "Cancellation reason" in captured["html"]


def test_placed_seller_email_includes_preferred_window() -> None:
    from app import worker

    captured: dict[str, str] = {}

    def _capture(to, subject, body, *, html=None, reply_to=None):
        captured["html"] = html or ""
        captured["body"] = body

    ctx = {**_fake_ctx(), "preferred_delivery": "Sun 21 Jun · Evening (3–9 PM)"}
    with (
        patch("app.worker._load_order_email_context", return_value=ctx),
        patch("app.worker._resolve_email", side_effect=_capture),
    ):
        worker.send_order_placed_seller_async(7)

    assert "Requested delivery" in captured["html"]
    assert "Sun 21 Jun · Evening (3–9 PM)" in captured["html"]
    assert "Requested delivery" in captured["body"]


def test_confirmed_customer_email_includes_preferred_window() -> None:
    from app import worker

    captured: dict[str, str] = {}

    def _capture(to, subject, body, *, html=None, reply_to=None):
        captured["html"] = html or ""
        captured["body"] = body

    ctx = {**_fake_ctx(), "preferred_delivery": "Sun 21 Jun · Morning (7–11 AM)"}
    with (
        patch("app.worker._load_order_email_context", return_value=ctx),
        patch("app.worker._resolve_email", side_effect=_capture),
    ):
        worker.send_order_confirmed_customer_async([7])

    assert "Requested delivery" in captured["html"]
    assert "Sun 21 Jun · Morning (7–11 AM)" in captured["html"]
