import logging
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    async def send_otp(self, to: str, code: str) -> None: ...


class ConsoleEmailSender:
    async def send_otp(self, to: str, code: str) -> None:
        logger.info("OTP for %s: %s", to, code)
        print(f"[OTP] {to} → {code}")


class ResendEmailSender:
    async def send_otp(self, to: str, code: str) -> None:
        payload = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to],
            "subject": "Your Khana Bazaar login code",
            "text": f"Your login code is: {code}\n\nThis code expires in 10 minutes.",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                timeout=10.0,
            )
            response.raise_for_status()


@lru_cache(maxsize=1)
def get_email_sender() -> EmailSender:
    if settings.EMAIL_PROVIDER == "resend":
        return ResendEmailSender()
    return ConsoleEmailSender()
