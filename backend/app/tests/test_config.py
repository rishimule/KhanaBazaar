# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import logging
import os
from importlib import reload


def _reload_with_env(env: dict[str, str]):
    """Reload the config module under a controlled env so the validator re-runs."""
    base_env = {
        # Required keys for Settings instantiation.
        "JWT_SECRET": "test-secret",
        "OTP_PEPPER": "test-pepper",
        "DATABASE_URL": "postgresql+asyncpg://x@localhost/x",
        "REDIS_URL": "redis://localhost:6379/0",
    }
    for key in list(os.environ):
        if key.startswith(("EMAIL_", "SUPPORT_EMAIL", "ENVIRONMENT")):
            del os.environ[key]
    for key, value in {**base_env, **env}.items():
        os.environ[key] = value

    import app.core.config as config_module

    reload(config_module)
    return config_module.settings


def test_default_email_reply_to_falls_back_to_support_email():
    s = _reload_with_env({"SUPPORT_EMAIL": "support@khanabazaar.in"})
    assert s.EMAIL_REPLY_TO == "support@khanabazaar.in"


def test_explicit_email_reply_to_overrides_support_email():
    s = _reload_with_env(
        {"SUPPORT_EMAIL": "support@khanabazaar.in", "EMAIL_REPLY_TO": "noreply@kb.in"}
    )
    assert s.EMAIL_REPLY_TO == "noreply@kb.in"


def test_support_email_example_in_production_emits_warning(caplog):
    caplog.set_level(logging.WARNING)
    _reload_with_env(
        {"ENVIRONMENT": "production", "SUPPORT_EMAIL": "support@khanabazaar.example"}
    )
    assert any(
        "SUPPORT_EMAIL" in record.message and ".example" in record.message
        for record in caplog.records
    )


def test_support_email_example_in_development_does_not_warn(caplog):
    caplog.set_level(logging.WARNING)
    _reload_with_env(
        {"ENVIRONMENT": "development", "SUPPORT_EMAIL": "support@khanabazaar.example"}
    )
    assert not any(
        "SUPPORT_EMAIL" in record.message and ".example" in record.message
        for record in caplog.records
    )


def test_brand_name_default():
    s = _reload_with_env({})
    assert s.EMAIL_BRAND_NAME == "Khana Bazaar"


def test_frontend_base_url_default():
    s = _reload_with_env({})
    assert s.EMAIL_FRONTEND_BASE_URL == "http://localhost:3000"
