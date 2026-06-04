# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from app.core.config import settings


def test_deploy_fields_exist_with_safe_defaults():
    # Dev OTP inbox is OFF unless explicitly enabled.
    assert settings.EXPOSE_DEV_OTPS is False
    assert settings.DEV_LOGS_USERNAME == ""
    assert settings.DEV_LOGS_PASSWORD == ""
