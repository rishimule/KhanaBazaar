"""Tests for SMS-provider settings in core.config."""
import importlib


def test_sms_provider_defaults_to_console(monkeypatch):
    monkeypatch.delenv("SMS_PROVIDER", raising=False)
    import app.core.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.SMS_PROVIDER == "console"


def test_sms_provider_accepts_twilio(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "twilio")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok_test")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15005550006")
    import app.core.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.SMS_PROVIDER == "twilio"
    assert cfg.settings.TWILIO_ACCOUNT_SID == "AC_test"
    assert cfg.settings.TWILIO_FROM_NUMBER == "+15005550006"
