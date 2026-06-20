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


class _RecordingWhatsApp:
    def __init__(self):
        self.calls = []

    async def send_template(self, to, template, variables):
        self.calls.append((to, template.name, variables))


def _run_status_task(ctx, *, status="dispatched", sender=None):
    """Drive send_order_status_whatsapp_async with patched sender + context.

    get_whatsapp_sender / STATUS_TEMPLATES are imported inside the task, so we
    patch them at their source module; _load_order_email_context is module-level
    on worker.
    """
    from app import worker

    with patch("app.core.whatsapp.get_whatsapp_sender", return_value=sender), \
         patch("app.worker._load_order_email_context", return_value=ctx):
        worker.send_order_status_whatsapp_async(42, status)


def test_order_status_whatsapp_sends_for_verified_phone():
    rec = _RecordingWhatsApp()
    _run_status_task(
        {"customer_phone": "+919999999999", "customer_phone_verified": True,
         "store_name": "Anand Stores"},
        sender=rec,
    )
    assert rec.calls == [
        ("+919999999999", "order_dispatched", {"order_no": "42", "store": "Anand Stores"})
    ]


def test_order_status_whatsapp_noop_for_unverified_phone():
    rec = _RecordingWhatsApp()
    _run_status_task(
        {"customer_phone": "+919999999999", "customer_phone_verified": False,
         "store_name": "Anand Stores"},
        sender=rec,
    )
    assert rec.calls == []


def test_order_status_whatsapp_noop_for_absent_phone():
    rec = _RecordingWhatsApp()
    _run_status_task(
        {"customer_phone": None, "customer_phone_verified": False}, sender=rec
    )
    assert rec.calls == []


def test_order_status_whatsapp_noop_when_disabled():
    # Disabled provider → sender is None → must not even load context.
    from app import worker

    with patch("app.core.whatsapp.get_whatsapp_sender", return_value=None), \
         patch("app.worker._load_order_email_context") as loader:
        worker.send_order_status_whatsapp_async(42, "dispatched")
    loader.assert_not_called()


def test_order_status_whatsapp_noop_for_unmapped_status():
    rec = _RecordingWhatsApp()
    # "paid" is a dormant OrderStatus value with no template.
    with patch("app.core.whatsapp.get_whatsapp_sender", return_value=rec), \
         patch("app.worker._load_order_email_context") as loader:
        from app import worker

        worker.send_order_status_whatsapp_async(42, "paid")
    assert rec.calls == []
    loader.assert_not_called()


def test_order_placed_whatsapp_includes_preferred_window():
    rec = _RecordingWhatsApp()
    _run_status_task(
        {"customer_phone": "+919999999999", "customer_phone_verified": True,
         "store_name": "Anand Stores",
         "preferred_delivery": "Sun 21 Jun · Evening (3–9 PM)",
         "delivery_eta": "30–60 min"},
        status="pending",
        sender=rec,
    )
    assert rec.calls == [
        ("+919999999999", "order_placed",
         {"order_no": "42", "store": "Anand Stores",
          "when": "Sun 21 Jun · Evening (3–9 PM)"})
    ]


def test_order_placed_whatsapp_falls_back_to_eta():
    rec = _RecordingWhatsApp()
    _run_status_task(
        {"customer_phone": "+919999999999", "customer_phone_verified": True,
         "store_name": "Anand Stores", "preferred_delivery": None,
         "delivery_eta": "30–60 min"},
        status="pending",
        sender=rec,
    )
    assert rec.calls[0][2]["when"] == "30–60 min"


def test_non_placed_whatsapp_has_no_when_variable():
    rec = _RecordingWhatsApp()
    _run_status_task(
        {"customer_phone": "+919999999999", "customer_phone_verified": True,
         "store_name": "Anand Stores"},
        status="dispatched",
        sender=rec,
    )
    assert "when" not in rec.calls[0][2]


def test_order_placed_template_declares_when_variable():
    assert TEMPLATES["order_placed"].variables == ("order_no", "store", "when")
