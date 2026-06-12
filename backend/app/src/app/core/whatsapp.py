# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""WhatsApp dispatch — sandbox via console, production via Twilio.

Mirrors `app.core.sms` / `app.core.email`: a Protocol + concrete impls + a
cached factory. WhatsApp is template-first — callers pass a registered
WhatsAppTemplate + variables, never raw text. `get_whatsapp_sender()` returns
None when WHATSAPP_PROVIDER == "none", which all callers treat as "disabled".
"""
import json
import logging
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.whatsapp_templates import WhatsAppTemplate

logger = logging.getLogger(__name__)


class WhatsAppSender(Protocol):
    async def send_template(
        self, to: str, template: WhatsAppTemplate, variables: dict[str, str]
    ) -> None: ...


class ConsoleWhatsAppSender:
    async def send_template(
        self, to: str, template: WhatsAppTemplate, variables: dict[str, str]
    ) -> None:
        body = template.render(variables)
        logger.info(
            "[WHATSAPP] to=%s template=%s (%s)\n%s",
            to, template.name, template.category, body,
        )
        print(
            f"[WHATSAPP] to={to} template={template.name} "
            f"({template.category})\n{body}"
        )
        # Dev-only capture (best-effort, ENVIRONMENT-gated inside).
        from app.core.dev_mailbox import record_outbound_whatsapp

        await record_outbound_whatsapp(
            to=to, body=body, template=template.name, category=template.category
        )


class TwilioWhatsAppSender:
    async def send_template(
        self, to: str, template: WhatsAppTemplate, variables: dict[str, str]
    ) -> None:
        # Twilio Content API. ContentSid is resolved at go-live from settings via
        # template.content_sid_setting; ContentVariables is positional ("1","2",
        # ...) ordered by template.variables.
        if template.content_sid_setting is None:
            raise RuntimeError(
                f"WhatsApp template {template.name!r} has no content_sid_setting; "
                "register its Twilio ContentSid before enabling the twilio provider"
            )
        content_sid = getattr(settings, template.content_sid_setting, "")
        content_vars = {
            str(i + 1): variables[key] for i, key in enumerate(template.variables)
        }
        url = (
            f"https://api.twilio.com/2010-04-01/Accounts/"
            f"{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                data={
                    "From": settings.TWILIO_WHATSAPP_FROM,
                    "To": f"whatsapp:{to}",
                    "ContentSid": content_sid,
                    "ContentVariables": json.dumps(content_vars),
                },
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                timeout=10.0,
            )
            response.raise_for_status()


@lru_cache(maxsize=1)
def get_whatsapp_sender() -> WhatsAppSender | None:
    if settings.WHATSAPP_PROVIDER == "twilio":
        return TwilioWhatsAppSender()
    if settings.WHATSAPP_PROVIDER == "console":
        return ConsoleWhatsAppSender()
    return None  # "none" → disabled
