# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Phone-OTP channel routing: WhatsApp-preferred, SMS fallback.

Decouples channel selection from copy: each call site supplies the WhatsApp
template name + variables AND its own verbatim SMS fallback text, so SMS-only
recipients (and the WHATSAPP_PROVIDER=none path) see unchanged behavior.
"""
import logging

from app.core.sms import SMSSender
from app.core.whatsapp import WhatsAppSender
from app.core.whatsapp_templates import TEMPLATES

logger = logging.getLogger(__name__)


async def deliver_phone_otp(
    *,
    to: str,
    template_name: str,
    variables: dict[str, str],
    sms_text: str,
    sms_sender: SMSSender,
    whatsapp_sender: WhatsAppSender | None,
) -> str:
    """Send the OTP over WhatsApp if enabled, else/then SMS. Returns the channel
    actually used ("whatsapp" | "sms")."""
    if whatsapp_sender is not None:
        try:
            await whatsapp_sender.send_template(
                to, TEMPLATES[template_name], variables
            )
            return "whatsapp"
        except Exception:  # noqa: BLE001 — any WhatsApp error → SMS fallback
            logger.warning(
                "WhatsApp OTP send failed (template=%s); falling back to SMS",
                template_name, exc_info=True,
            )
    await sms_sender.send(to=to, text=sms_text)
    return "sms"
