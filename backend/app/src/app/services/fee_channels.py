# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Best-effort fan-out of seller fee notifications to SMS + WhatsApp + email.
Post-commit only; broker-hiccup-safe via _safe_delay; each task no-ops when its
channel/contact is unavailable."""
from datetime import date

from app.services.order_emails import _safe_delay
from app.worker import (
    send_seller_fee_email_async,
    send_seller_fee_sms_async,
    send_seller_fee_whatsapp_async,
)


def dispatch_seller_fee_channels(
    seller_profile_id: int, type_value: str, valid_until: date | str | None = None
) -> None:
    """Enqueue best-effort SMS + WhatsApp + email for a seller fee event.
    Call AFTER the triggering event's DB commit."""
    until: str | None
    if valid_until is None:
        until = None
    elif isinstance(valid_until, str):
        until = valid_until
    else:
        until = valid_until.isoformat()
    _safe_delay(send_seller_fee_sms_async, seller_profile_id, type_value, until)
    _safe_delay(send_seller_fee_whatsapp_async, seller_profile_id, type_value, until)
    _safe_delay(send_seller_fee_email_async, seller_profile_id, type_value, until)
