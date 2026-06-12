# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Thin dispatcher for customer order-status WhatsApp messages.

Mirrors services/order_emails: wraps `.delay()` so a broker hiccup never breaks
the order path. Additive alongside email — fired from the notification
chokepoint in api/orders.record_and_dispatch_notification.
"""
from app.services.order_emails import _safe_delay
from app.worker import send_order_status_whatsapp_async


def dispatch_order_status_whatsapp(order_id: int, status: str) -> None:
    _safe_delay(send_order_status_whatsapp_async, order_id, status)
