# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""SMS dispatch — sandbox via console, production via Twilio.

Mirrors `app.core.email`: a Protocol + two concrete implementations + a
cached factory. The handler at `/auth/seller/phone/otp/request` injects
`SMSSender` via FastAPI's `Depends(get_sms_sender)` and dispatches inline.
"""
import logging
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class SMSSender(Protocol):
    async def send(self, to: str, text: str) -> None: ...


class ConsoleSMSSender:
    async def send(self, to: str, text: str) -> None:
        logger.info("[SMS] to=%s\n%s", to, text)
        print(f"[SMS] to={to}\n{text}")
        # Dev-only capture into the dev_sms table (best-effort). Covers BOTH the
        # inline seller-phone OTP and the worker delivery-OTP SMS, since both
        # route through get_sms_sender().send().
        from app.core.dev_mailbox import record_outbound_sms

        await record_outbound_sms(to=to, text=text)


class TwilioSMSSender:
    async def send(self, to: str, text: str) -> None:
        url = (
            f"https://api.twilio.com/2010-04-01/Accounts/"
            f"{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                data={
                    "From": settings.TWILIO_FROM_NUMBER,
                    "To": to,
                    "Body": text,
                },
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                timeout=10.0,
            )
            response.raise_for_status()


@lru_cache(maxsize=1)
def get_sms_sender() -> SMSSender:
    if settings.SMS_PROVIDER == "twilio":
        return TwilioSMSSender()
    return ConsoleSMSSender()
