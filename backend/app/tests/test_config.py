# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Settings validator + new email-related fields.

Tests instantiate ``Settings`` directly with kwargs to avoid mutating the
shared ``app.core.config.settings`` singleton (which other tests depend on).
"""
import logging

from app.core.config import Settings

_REQUIRED = {
    "JWT_SECRET": "test-secret",
    "OTP_PEPPER": "test-pepper",
    "DATABASE_URL": "postgresql+asyncpg://x@localhost/x",
    "REDIS_URL": "redis://localhost:6379/0",
}


def _make(**overrides):
    return Settings(_env_file=None, **_REQUIRED, **overrides)


def test_default_email_reply_to_falls_back_to_support_email():
    s = _make(SUPPORT_EMAIL="support@khanabazaar.in")
    assert s.EMAIL_REPLY_TO == "support@khanabazaar.in"


def test_explicit_email_reply_to_overrides_support_email():
    s = _make(SUPPORT_EMAIL="support@khanabazaar.in", EMAIL_REPLY_TO="noreply@kb.in")
    assert s.EMAIL_REPLY_TO == "noreply@kb.in"


def test_support_email_example_in_production_emits_warning(caplog):
    caplog.set_level(logging.WARNING)
    _make(ENVIRONMENT="production", SUPPORT_EMAIL="support@khanabazaar.example")
    assert any(
        "SUPPORT_EMAIL" in record.message and ".example" in record.message
        for record in caplog.records
    )


def test_support_email_example_in_development_does_not_warn(caplog):
    caplog.set_level(logging.WARNING)
    _make(ENVIRONMENT="development", SUPPORT_EMAIL="support@khanabazaar.example")
    assert not any(
        "SUPPORT_EMAIL" in record.message and ".example" in record.message
        for record in caplog.records
    )


def test_brand_name_default():
    s = _make()
    assert s.EMAIL_BRAND_NAME == "Khanabazaar"


def test_company_name_default():
    s = _make()
    assert s.COMPANY_NAME == "Khanabazaar"


def test_email_brand_name_defaults_to_company_name():
    s = _make(COMPANY_NAME="Acme Foods")
    assert s.EMAIL_BRAND_NAME == "Acme Foods"


def test_explicit_email_brand_name_overrides_company_name():
    s = _make(COMPANY_NAME="Acme Foods", EMAIL_BRAND_NAME="Acme Mail")
    assert s.EMAIL_BRAND_NAME == "Acme Mail"


def test_project_name_defaults_from_company_name():
    s = _make(COMPANY_NAME="Acme Foods")
    assert s.PROJECT_NAME == "Acme Foods API"


def test_explicit_project_name_overrides_company_name():
    s = _make(PROJECT_NAME="Custom API")
    assert s.PROJECT_NAME == "Custom API"


def test_frontend_base_url_default():
    s = _make()
    assert s.EMAIL_FRONTEND_BASE_URL == "http://localhost:3000"
