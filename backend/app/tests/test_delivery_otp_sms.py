# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""The delivery-handover code goes to the customer's phone only when that
number is verified — like return codes and WhatsApp order updates. Every new
customer now carries a phone, taken on trust while PHONE_OTP_ENABLED is off;
the code always arrives by email too (spec 2026-10-08 §8)."""
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app import worker


@pytest.mark.parametrize(
    ("ctx", "sent"),
    [
        ({"customer_phone": "+919876543210", "customer_phone_verified": True}, True),
        ({"customer_phone": "+919876543210", "customer_phone_verified": False}, False),
        ({"customer_phone": None, "customer_phone_verified": False}, False),
    ],
)
def test_delivery_code_texts_only_a_verified_number(
    monkeypatch: pytest.MonkeyPatch, ctx: dict[str, Any], sent: bool
) -> None:
    deliver = AsyncMock(return_value="sms")
    monkeypatch.setattr(worker, "_load_order_email_context", lambda _order_id: ctx)
    monkeypatch.setattr("app.core.otp_delivery.deliver_phone_otp", deliver)

    worker.send_delivery_otp_sms_async(42, "123456")

    assert deliver.await_count == (1 if sent else 0)
