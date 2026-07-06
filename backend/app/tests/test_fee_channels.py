# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from unittest.mock import patch

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


def test_dispatch_enqueues_all_channels() -> None:
    from app.services import fee_channels

    with patch.object(fee_channels, "_safe_delay") as sd:
        fee_channels.dispatch_seller_fee_channels(1, "fee_activated", "2026-10-01")
    # SMS + WhatsApp + email → 3 enqueues.
    assert sd.call_count == 3
