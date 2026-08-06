# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Phone-OTP channel routing: WhatsApp-preferred, SMS fallback.

Thin OTP-named delegate over core.phone_delivery.deliver_phone_message so the
channel-routing rule lives in exactly one place.
"""
from app.core.phone_delivery import deliver_phone_message
from app.core.sms import SMSSender
from app.core.whatsapp import WhatsAppSender


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
    return await deliver_phone_message(
        to=to,
        template_name=template_name,
        variables=variables,
        sms_text=sms_text,
        sms_sender=sms_sender,
        whatsapp_sender=whatsapp_sender,
    )
