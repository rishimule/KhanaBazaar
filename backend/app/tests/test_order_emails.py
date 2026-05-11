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
        "order_status": "pending",
        "service_name": service_name,
        "store_name": "Test Store",
        "seller_email": "seller@example.com",
        "customer_email": "customer@example.com",
    }


def test_placed_seller_email_includes_service_name() -> None:
    from app import worker

    captured: dict[str, str] = {}

    def _capture(to: str, subject: str, body: str) -> None:
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body

    with (
        patch("app.worker._load_order_email_context", return_value=_fake_ctx()),
        patch("app.worker._resolve_email", side_effect=_capture),
    ):
        worker.send_order_placed_seller_async(7)

    assert captured["to"] == "seller@example.com"
    assert "Grocery" in captured["subject"]
    assert "Test Store" in captured["subject"]
    assert "Grocery" in captured["body"]
    assert "#7" in captured["body"]


def test_confirmed_customer_email_includes_service_name() -> None:
    from app import worker

    captured: dict[str, str] = {}

    def _capture(to: str, subject: str, body: str) -> None:
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body

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

    def _capture(to: str, subject: str, body: str) -> None:
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body

    with (
        patch("app.worker._load_order_email_context", return_value=_fake_ctx()),
        patch("app.worker._resolve_email", side_effect=_capture),
    ):
        worker.send_order_status_changed_async(7, "packed", recipient)

    assert captured["to"] == expected_to
    assert "Grocery" in captured["subject"]
    assert "packed" in captured["subject"]
    assert "Grocery" in captured["body"]
    assert "#7" in captured["body"]
