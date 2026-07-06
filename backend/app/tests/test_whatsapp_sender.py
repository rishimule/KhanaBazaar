# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import pytest

from app.core.whatsapp_templates import STATUS_TEMPLATES, TEMPLATES, WhatsAppTemplate


def test_whatsapp_provider_defaults_to_none():
    # Assert the declared code default directly — independent of the dev .env
    # (which sets console) and OS env, and without instantiating Settings (whose
    # required fields would fail without an env file).
    from app.core.config import Settings

    assert Settings.model_fields["WHATSAPP_PROVIDER"].default == "none"


def test_twilio_whatsapp_from_defaults_empty():
    from app.core.config import Settings

    assert Settings.model_fields["TWILIO_WHATSAPP_FROM"].default == ""


def test_registry_has_all_templates():
    expected = {
        "otp_login", "otp_seller_phone", "otp_delivery",
        "order_placed", "order_packed", "order_dispatched",
        "order_delivered", "order_cancelled",
        "fee_activated", "fee_expiring", "fee_suspended",
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


def test_get_whatsapp_sender_none_when_disabled(monkeypatch):
    from app.core import whatsapp as whatsapp_mod

    monkeypatch.setattr(whatsapp_mod.settings, "WHATSAPP_PROVIDER", "none")
    whatsapp_mod.get_whatsapp_sender.cache_clear()
    assert whatsapp_mod.get_whatsapp_sender() is None
    whatsapp_mod.get_whatsapp_sender.cache_clear()


def test_get_whatsapp_sender_console(monkeypatch):
    from app.core import whatsapp as whatsapp_mod

    monkeypatch.setattr(whatsapp_mod.settings, "WHATSAPP_PROVIDER", "console")
    whatsapp_mod.get_whatsapp_sender.cache_clear()
    sender = whatsapp_mod.get_whatsapp_sender()
    assert isinstance(sender, whatsapp_mod.ConsoleWhatsAppSender)
    whatsapp_mod.get_whatsapp_sender.cache_clear()


@pytest.mark.asyncio
async def test_console_sender_renders_and_captures(session, monkeypatch):
    from sqlmodel import select

    from app.core.config import settings as cfg
    from app.core.whatsapp import ConsoleWhatsAppSender
    from app.models.dev_whatsapp import DevWhatsApp

    monkeypatch.setattr(cfg, "ENVIRONMENT", "development")
    await ConsoleWhatsAppSender().send_template(
        "+918888888888", TEMPLATES["otp_login"], {"code": "654321"}
    )
    rows = (await session.exec(select(DevWhatsApp))).all()
    assert len(rows) == 1
    assert "654321" in rows[0].body
    assert rows[0].template == "otp_login"
    assert rows[0].category == "AUTHENTICATION"


@pytest.mark.asyncio
async def test_twilio_sender_raises_without_content_sid():
    # All shipped templates leave content_sid_setting=None, so the twilio
    # provider must fail loud (caught upstream → SMS fallback) until ContentSids
    # are registered at go-live.
    from app.core.whatsapp import TwilioWhatsAppSender

    with pytest.raises(RuntimeError):
        await TwilioWhatsAppSender().send_template(
            "+919999999999", TEMPLATES["otp_login"], {"code": "1"}
        )


@pytest.mark.asyncio
async def test_twilio_sender_builds_positional_content_variables(monkeypatch):
    import json

    from app.core import whatsapp as wmod

    captured: dict = {}

    class _Resp:
        def raise_for_status(self) -> None:
            pass

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return _Resp()

    class _FakeSettings:
        TWILIO_ACCOUNT_SID = "AC_test"
        TWILIO_AUTH_TOKEN = "tok"
        TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886"
        WA_TEST_SID = "HX123"

    monkeypatch.setattr(wmod.httpx, "AsyncClient", _Client)
    # Replace the whole settings ref (pydantic Settings rejects setting a
    # non-field attr like WA_TEST_SID).
    monkeypatch.setattr(wmod, "settings", _FakeSettings())

    tmpl = WhatsAppTemplate(
        name="t", category="UTILITY", variables=("order_no", "store"),
        render=lambda v: "x", content_sid_setting="WA_TEST_SID",
    )
    await wmod.TwilioWhatsAppSender().send_template(
        "+919999999999", tmpl, {"order_no": "42", "store": "Anand"}
    )

    data = captured["data"]
    assert data["To"] == "whatsapp:+919999999999"
    assert data["From"] == "whatsapp:+14155238886"
    assert data["ContentSid"] == "HX123"
    assert json.loads(data["ContentVariables"]) == {"1": "42", "2": "Anand"}
