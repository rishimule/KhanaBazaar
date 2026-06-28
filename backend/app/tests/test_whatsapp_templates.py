# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest

from app.core.config import settings
from app.core.whatsapp_templates import TEMPLATES


@pytest.mark.parametrize(
    "key,variables",
    [
        ("otp_login", {"code": "123456"}),
        ("otp_seller_phone", {"code": "123456"}),
        ("otp_delivery", {"order_no": "42", "code": "123456"}),
    ],
)
def test_otp_templates_render_uses_company_name(monkeypatch, key, variables):
    monkeypatch.setattr(settings, "COMPANY_NAME", "Acme Foods")
    out = TEMPLATES[key].render(variables)
    assert "Acme Foods" in out
    assert "Khana Bazaar" not in out
