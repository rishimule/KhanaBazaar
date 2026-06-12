# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from unittest.mock import patch

from app.core.whatsapp_templates import STATUS_TEMPLATES, TEMPLATES


def test_status_templates_cover_all_notification_statuses():
    # The 5 statuses passed to record_and_dispatch_notification.
    for status in ("pending", "packed", "dispatched", "delivered", "cancelled"):
        assert status in STATUS_TEMPLATES
        assert STATUS_TEMPLATES[status] in TEMPLATES.values()


def test_dispatcher_uses_safe_delay():
    from app.services import order_whatsapp

    with patch.object(order_whatsapp, "_safe_delay") as m:
        order_whatsapp.dispatch_order_status_whatsapp(7, "dispatched")
    m.assert_called_once_with(
        order_whatsapp.send_order_status_whatsapp_async, 7, "dispatched"
    )
