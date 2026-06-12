# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from app.core.config import settings


def test_whatsapp_provider_defaults_to_none():
    assert settings.WHATSAPP_PROVIDER == "none"


def test_twilio_whatsapp_from_defaults_empty():
    assert settings.TWILIO_WHATSAPP_FROM == ""
