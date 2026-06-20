# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.schemas.orders import PlaceOrderRequest
from app.utils.delivery_window import ist_today

BASE = {"customer_address_id": 1, "store_id": 1, "service_id": 1, "payment_method": "upi"}


def test_accepts_no_preference():
    req = PlaceOrderRequest(**BASE)
    assert req.preferred_delivery_date is None
    assert req.preferred_delivery_window is None


def test_accepts_valid_preference():
    d = ist_today() + timedelta(days=1)
    req = PlaceOrderRequest(
        **BASE, preferred_delivery_date=d.isoformat(), preferred_delivery_window="evening"
    )
    assert req.preferred_delivery_date == d
    assert req.preferred_delivery_window == "evening"


def test_rejects_only_date():
    d = ist_today().isoformat()
    with pytest.raises(ValidationError):
        PlaceOrderRequest(**BASE, preferred_delivery_date=d)


def test_rejects_unknown_window():
    d = ist_today().isoformat()
    with pytest.raises(ValidationError):
        PlaceOrderRequest(
            **BASE, preferred_delivery_date=d, preferred_delivery_window="night"
        )


def test_rejects_past_date():
    d = (ist_today() - timedelta(days=1)).isoformat()
    with pytest.raises(ValidationError):
        PlaceOrderRequest(
            **BASE, preferred_delivery_date=d, preferred_delivery_window="morning"
        )
