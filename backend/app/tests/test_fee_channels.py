# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from app.core.whatsapp_templates import FEE_TEMPLATES, TEMPLATES


def test_fee_templates_registered() -> None:
    for key in ("fee_activated", "fee_expiring", "fee_suspended"):
        assert key in TEMPLATES
        assert TEMPLATES[key].category == "UTILITY"
    # FEE_TEMPLATES keyed by NotificationType value.
    assert FEE_TEMPLATES["fee_expiring"].name == "fee_expiring"


def test_fee_expiring_render_includes_date() -> None:
    text = TEMPLATES["fee_expiring"].render({"until": "2026-10-01"})
    assert "2026-10-01" in text
