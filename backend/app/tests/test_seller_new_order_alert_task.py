# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from unittest.mock import patch

from app.core.whatsapp_templates import TEMPLATES


def test_seller_new_order_template_registered() -> None:
    tmpl = TEMPLATES["seller_new_order"]
    assert tmpl.category == "UTILITY"
    assert set(tmpl.variables) == {"order_id", "amount"}
    rendered = tmpl.render({"order_id": "42", "amount": "350.00"})
    assert "#42" in rendered
    assert "350.00" in rendered


def test_dispatch_order_placed_fires_the_seller_alert() -> None:
    from app.services import order_emails

    with patch.object(order_emails, "_safe_delay") as safe_delay:
        order_emails.dispatch_order_placed([7])

    dispatched = [c.args[0].name for c in safe_delay.call_args_list]
    assert "send_seller_new_order_alert_async" in dispatched
