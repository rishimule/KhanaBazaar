# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from app.models.commerce import DeliveryMode, PaymentMethod


def test_delivery_mode_values() -> None:
    assert DeliveryMode.DoorDelivery.value == "door_delivery"
    assert DeliveryMode.Pickup.value == "pickup"


def test_payment_method_new_values() -> None:
    assert PaymentMethod.NetBanking.value == "net_banking"
    assert PaymentMethod.PayAtStore.value == "pay_at_store"
    assert {m.value for m in PaymentMethod} == {
        "upi",
        "cash",
        "credit",
        "net_banking",
        "pay_at_store",
    }
