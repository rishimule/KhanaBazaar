# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Tests for SMS-provider settings in core.config."""
import importlib

import pytest


def test_sms_provider_defaults_to_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SMS_PROVIDER", raising=False)
    import app.core.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.SMS_PROVIDER == "console"


def test_sms_provider_accepts_twilio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMS_PROVIDER", "twilio")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok_test")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15005550006")
    import app.core.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.SMS_PROVIDER == "twilio"
    assert cfg.settings.TWILIO_ACCOUNT_SID == "AC_test"
    assert cfg.settings.TWILIO_FROM_NUMBER == "+15005550006"
