# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from app.core.config import settings


def test_session_settings_defaults() -> None:
    assert settings.ACCESS_TOKEN_TTL_MINUTES == 15
    assert settings.SESSION_UNTRUSTED_TTL_HOURS == 24
    assert settings.SESSION_CUSTOMER_IDLE_DAYS == 30
    assert settings.SESSION_CUSTOMER_MAX_DAYS == 180
    assert settings.SESSION_SELLER_IDLE_DAYS == 14
    assert settings.SESSION_SELLER_MAX_DAYS == 90
    assert settings.SESSION_ADMIN_IDLE_DAYS == 7
    assert settings.SESSION_ADMIN_MAX_DAYS == 30
    assert settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS == 30
