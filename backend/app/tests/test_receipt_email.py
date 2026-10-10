# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""The receipt email (spec 2026-10-10 §6)."""
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Retry
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.email_render import render_email
from app.core.security import get_current_user
from app.models.base import AccountStatus, User
from app.models.receipt import OrderReceipt
from app.services.receipts import email_context
from tests.test_orders import (  # noqa: F401
    _deliver_with_otp,
    _order_id_for_store,
    _place_orders,
    as_customer,
    mock_customer,
    mock_seller,
    seed,
)

ISSUED = datetime(2026, 10, 10, 9, 30, tzinfo=timezone.utc)


def _snapshot(**amount_overrides: float) -> dict[str, Any]:
    amounts: dict[str, Any] = {
        "subtotal": 100.0,
        "delivery_fee": 10.0,
        "delivery_fee_kind": "delivery",
        "total": 110.0,
        "store_credit_applied": 0.0,
        "amount_paid": 110.0,
        **amount_overrides,
    }
    return {
        "version": 1,
        "order": {
            "id": 7,
            "placed_at": "2026-10-10T08:00:00+00:00",
            "delivered_at": ISSUED.isoformat(),
            "delivery_mode": "door_delivery",
            "service_name": "Grocery",
        },
        "seller": {
            "business_name": "S1 Traders",
            "store_name": "Store A",
            "store_address": "1 Market St, Bengaluru",
            "gstin": "29ABCDE1234F1Z5",
            "fssai": None,
        },
        "customer": {"name": "Asha Rao", "phone": "+919800000001"},
        "deliver_to": {"name": None, "phone": None, "address": "12 MG Road, Bengaluru"},
        "items": [{"name": "Apple", "quantity": 2, "unit_price": 50.0, "line_total": 100.0}],
        "amounts": amounts,
        "payment": {"method": "upi", "settled": "paid", "paid_at": ISSUED.isoformat()},
    }


def _receipt(via: str = "delivery", **amount_overrides: float) -> OrderReceipt:
    return OrderReceipt(
        id=1,
        order_id=7,
        store_id=3,
        fiscal_year=2026,
        seq=45,
        number="RC-2627-000045",
        issued_at=ISSUED,
        issued_via=via,
        snapshot_version=1,
        snapshot=_snapshot(**amount_overrides),
        created_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize("recipient", ["customer", "seller"])
def test_receipt_renders_for_both_recipients(recipient: str) -> None:
    payload = render_email("order_receipt", {**email_context(_receipt()), "recipient": recipient})
    for part in (payload.html, payload.text):
        assert "RC-2627-000045" in part
        assert "S1 Traders" in part and "GSTIN: 29ABCDE1234F1Z5" in part
        assert "Asha Rao" in part and "Apple" in part
        assert "Paid ₹110.00 · UPI" in part
        assert "not a tax invoice" in part
        assert f"/{'seller' if recipient == 'seller' else 'account'}/orders/7/receipt" in part
    if recipient == "seller":
        assert payload.subject.endswith("Seller copy: receipt RC-2627-000045 · order #7")
        assert "Seller copy" in payload.html
    else:
        assert payload.subject.endswith("Your receipt for order #7 from Store A")
        assert "Seller copy" not in payload.html


def test_backfilled_receipt_says_so_and_store_credit_shows() -> None:
    payload = render_email(
        "order_receipt",
        {
            **email_context(_receipt(via="backfill", store_credit_applied=30.0, amount_paid=80.0)),
            "recipient": "customer",
        },
    )
    assert "Issued from order records on 02 Nov 2026" in payload.text
    assert "Store credit used" in payload.text and "−₹30.00" in payload.text
    assert "Paid ₹80.00 · UPI" in payload.text


def test_pickup_text_reads_cleanly() -> None:
    receipt = _receipt()
    receipt.snapshot["order"]["delivery_mode"] = "pickup"
    receipt.snapshot["deliver_to"] = None
    text = render_email("order_receipt", {**email_context(receipt), "recipient": "seller"}).text
    lines = text.splitlines()
    assert lines[0] == "SELLER COPY"
    assert "Collected at: Store A" in lines
    assert not any(line.startswith("Delivery:") for line in lines)
    assert "Collected — order #7 · Grocery" in lines


def test_empty_deliver_to_block_is_skipped() -> None:
    receipt = _receipt()
    receipt.snapshot["deliver_to"] = {"name": None, "phone": None, "address": None}
    payload = render_email("order_receipt", {**email_context(receipt), "recipient": "customer"})
    assert "Delivered to" not in payload.html and "Delivered to" not in payload.text


def test_phone_without_a_name_still_shows() -> None:
    receipt = _receipt()
    receipt.snapshot["deliver_to"] = {"name": None, "phone": "+919811111111", "address": None}
    text = render_email("order_receipt", {**email_context(receipt), "recipient": "customer"}).text
    assert "Delivered to: +919811111111" in text.splitlines()


def test_store_name_printed_once_when_it_is_the_business_name() -> None:
    receipt = _receipt()
    receipt.snapshot["seller"]["business_name"] = "Store A"
    lines = render_email(
        "order_receipt", {**email_context(receipt), "recipient": "customer"}
    ).text.splitlines()
    assert "Sold by: Store A" in lines
    assert "1 Market St, Bengaluru" in lines
    html = render_email("order_receipt", {**email_context(receipt), "recipient": "customer"}).html
    assert html.count("Store A") == 2  # the "Sold by" name + the subject in <title>


async def _deliver(seed: dict[str, int]) -> int:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert (await _deliver_with_otp(ac, target)).status_code == 200
    return target


async def test_delivered_task_sends_receipts_to_both(as_customer: Any, seed: dict[str, int]) -> None:
    from app import worker

    target = await _deliver(seed)
    sent = MagicMock()
    with patch("app.worker._resolve_email", sent):
        worker.send_order_status_changed_async(target, "delivered", "customer")
        worker.send_order_status_changed_async(target, "delivered", "seller")
    recipients = [c.args[0] for c in sent.call_args_list]
    subjects = [c.args[1] for c in sent.call_args_list]
    assert recipients == [mock_customer.email, mock_seller.email]
    assert "Your receipt for order" in subjects[0]
    assert "Seller copy: receipt" in subjects[1]


async def test_inactive_customer_gets_no_receipt(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    from app import worker

    target = await _deliver(seed)
    customer = await session.get(User, mock_customer.id)
    assert customer is not None
    customer.account_status = AccountStatus.suspended
    customer.is_active = False
    session.add(customer)
    await session.commit()
    sent = MagicMock()
    with patch("app.worker._resolve_email", sent):
        worker.send_order_status_changed_async(target, "delivered", "customer")
    sent.assert_not_called()


async def test_inactive_seller_gets_no_copy(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    from app import worker

    target = await _deliver(seed)
    seller = await session.get(User, mock_seller.id)
    assert seller is not None
    seller.is_active = False
    session.add(seller)
    await session.commit()
    sent = MagicMock()
    with patch("app.worker._resolve_email", sent):
        worker.send_order_status_changed_async(target, "delivered", "seller")
    sent.assert_not_called()


async def test_broken_receipt_falls_back_to_the_plain_email(
    as_customer: Any, seed: dict[str, int]
) -> None:
    from app import worker
    from tests.test_order_emails import _fake_ctx

    target = await _deliver(seed)
    sent = MagicMock()
    with (
        patch("app.services.receipts.email_context", side_effect=RuntimeError("boom")),
        patch("app.worker._load_order_email_context", return_value=_fake_ctx(order_id=target)),
        patch("app.worker._resolve_email", sent),
    ):
        worker.send_order_status_changed_async(target, "delivered", "customer")
        worker.send_order_status_changed_async(target, "delivered", "seller")
    # The customer still hears the order arrived; sellers never got the
    # plain "delivered" email, so a broken receipt sends them nothing.
    assert [c.args[0] for c in sent.call_args_list] == ["customer@example.com"]
    assert "is now delivered" in sent.call_args.args[1]


async def test_failed_send_retries_instead_of_falling_back(
    as_customer: Any, seed: dict[str, int]
) -> None:
    from app import worker

    target = await _deliver(seed)
    sent = MagicMock(side_effect=ConnectionError("smtp down"))
    plain = MagicMock()
    with (
        patch("app.worker._resolve_email", sent),
        patch("app.worker._load_order_email_context", plain),
        pytest.raises((ConnectionError, Retry)),
    ):
        worker.send_order_status_changed_async(target, "delivered", "customer")
    # The receipt send was attempted and raised into Celery's retry; the
    # plain email was never built, so a retry can't double up.
    assert sent.call_count >= 1
    assert all("Your receipt for order" in c.args[1] for c in sent.call_args_list)
    plain.assert_not_called()


def test_database_blip_retries_instead_of_falling_back() -> None:
    from sqlalchemy.exc import OperationalError

    from app import worker

    plain = MagicMock()
    with (
        patch(
            "app.services.receipts.load_receipt_mail",
            side_effect=OperationalError("SELECT 1", {}, Exception("connection reset")),
        ),
        patch("app.worker._load_order_email_context", plain),
        pytest.raises((OperationalError, Retry)),
    ):
        worker.send_order_status_changed_async(7, "delivered", "customer")
    plain.assert_not_called()


def test_no_receipt_falls_back_to_the_status_email() -> None:
    from app import worker
    from tests.test_order_emails import _fake_ctx

    sent = MagicMock()
    with (
        patch("app.worker._load_order_email_context", return_value=_fake_ctx(order_id=999_999)),
        patch("app.worker._resolve_email", sent),
    ):
        worker.send_order_status_changed_async(999_999, "delivered", "customer")
    sent.assert_called_once()
    assert "is now delivered" in sent.call_args.args[1]


def test_delivered_dispatch_includes_the_seller() -> None:
    from app.services import order_emails
    from app.worker import send_order_status_changed_async

    delay = MagicMock()
    with (
        patch.object(send_order_status_changed_async, "delay", delay),
        patch.object(order_emails, "dispatch_order_review_request"),
    ):
        order_emails.dispatch_order_status_changed(5, "delivered")
        order_emails.dispatch_order_status_changed(6, "packed")
    assert [c.args for c in delay.call_args_list] == [
        (5, "delivered", "customer", None),
        (5, "delivered", "seller", None),
        (6, "packed", "customer", None),
    ]
