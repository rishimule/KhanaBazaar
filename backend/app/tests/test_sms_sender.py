"""Tests for the SMSSender protocol and factory."""
import pytest

from app.core.sms import (
    ConsoleSMSSender,
    TwilioSMSSender,
)


@pytest.mark.anyio
async def test_console_sender_does_not_raise():
    sender = ConsoleSMSSender()
    await sender.send(to="+919876543210", text="hello")


def test_factory_returns_console_by_default(monkeypatch):
    from app.core import sms as sms_module

    sms_module.get_sms_sender.cache_clear()
    monkeypatch.setattr(sms_module.settings, "SMS_PROVIDER", "console")
    assert isinstance(sms_module.get_sms_sender(), ConsoleSMSSender)


def test_factory_returns_twilio_when_configured(monkeypatch):
    from app.core import sms as sms_module

    sms_module.get_sms_sender.cache_clear()
    monkeypatch.setattr(sms_module.settings, "SMS_PROVIDER", "twilio")
    assert isinstance(sms_module.get_sms_sender(), TwilioSMSSender)
    sms_module.get_sms_sender.cache_clear()
