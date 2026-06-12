# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from app.core.config import settings
from app.core.whatsapp_templates import STATUS_TEMPLATES, TEMPLATES


def test_whatsapp_provider_defaults_to_none():
    assert settings.WHATSAPP_PROVIDER == "none"


def test_twilio_whatsapp_from_defaults_empty():
    assert settings.TWILIO_WHATSAPP_FROM == ""


def test_registry_has_all_templates():
    expected = {
        "otp_login", "otp_seller_phone", "otp_delivery",
        "order_placed", "order_packed", "order_dispatched",
        "order_delivered", "order_cancelled",
    }
    assert set(TEMPLATES) == expected


def test_auth_templates_are_authentication_category():
    for name in ("otp_login", "otp_seller_phone", "otp_delivery"):
        assert TEMPLATES[name].category == "AUTHENTICATION"


def test_order_templates_are_utility_category():
    for name in ("order_placed", "order_packed", "order_dispatched",
                 "order_delivered", "order_cancelled"):
        assert TEMPLATES[name].category == "UTILITY"


def test_render_otp_login():
    text = TEMPLATES["otp_login"].render({"code": "123456"})
    assert "123456" in text


def test_render_order_dispatched():
    text = TEMPLATES["order_dispatched"].render(
        {"order_no": "42", "store": "Anand Stores"}
    )
    assert "42" in text and "Anand Stores" in text


def test_status_templates_map_each_notification_status():
    assert STATUS_TEMPLATES == {
        "pending": TEMPLATES["order_placed"],
        "packed": TEMPLATES["order_packed"],
        "dispatched": TEMPLATES["order_dispatched"],
        "delivered": TEMPLATES["order_delivered"],
        "cancelled": TEMPLATES["order_cancelled"],
    }
