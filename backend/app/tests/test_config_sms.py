# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Tests for SMS-provider settings in core.config.

Instantiates ``Settings`` directly instead of ``importlib.reload``-ing the
module — same rule as test_config.py, and for a sharper reason than tidiness.
A reload rebinds ``app.core.config.settings`` to a NEW object, while every
module that did ``from app.core.config import settings`` at import time keeps
the OLD one. Any code that imports settings lazily (``worker._resolve_email``,
for one) then reads the new object, so a later
``monkeypatch.setattr(settings, ...)`` silently fails to reach it and the test
sees whatever the real ``.env`` says. The reload leaked for the rest of the
session, so this broke unrelated tests hundreds of files later.
"""
import pytest

from app.core.config import Settings

_REQUIRED = {
    "JWT_SECRET": "test-secret",
    "OTP_PEPPER": "test-pepper",
    "DATABASE_URL": "postgresql+asyncpg://x@localhost/x",
    "REDIS_URL": "redis://localhost:6379/0",
}


def _from_env() -> Settings:
    """Build Settings from os.environ only, so monkeypatch.setenv drives the
    assertions and the repo's own .env cannot mask them."""
    return Settings(_env_file=None, **_REQUIRED)


def test_sms_provider_defaults_to_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SMS_PROVIDER", raising=False)
    assert _from_env().SMS_PROVIDER == "console"


def test_sms_provider_accepts_twilio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMS_PROVIDER", "twilio")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok_test")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15005550006")
    s = _from_env()
    assert s.SMS_PROVIDER == "twilio"
    assert s.TWILIO_ACCOUNT_SID == "AC_test"
    assert s.TWILIO_FROM_NUMBER == "+15005550006"
