import logging
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    async def send(self, to: str, subject: str, text: str) -> None: ...


class ConsoleEmailSender:
    async def send(self, to: str, subject: str, text: str) -> None:
        logger.info("[EMAIL] to=%s subject=%r\n%s", to, subject, text)
        print(f"[EMAIL] to={to}\n{text}")


class ResendEmailSender:
    async def send(self, to: str, subject: str, text: str) -> None:
        payload = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "text": text,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                timeout=10.0,
            )
            response.raise_for_status()


class ResendWithConsoleSender:
    def __init__(self) -> None:
        self._console = ConsoleEmailSender()
        self._resend = ResendEmailSender()

    async def send(self, to: str, subject: str, text: str) -> None:
        await self._console.send(to, subject, text)
        try:
            await self._resend.send(to, subject, text)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "[EMAIL] Resend rejected to=%s status=%s body=%s (console fallback already logged)",
                to,
                exc.response.status_code,
                exc.response.text,
            )


@lru_cache(maxsize=1)
def get_email_sender() -> EmailSender:
    if settings.EMAIL_PROVIDER == "resend":
        return ResendEmailSender()
    if settings.EMAIL_PROVIDER == "resend+console":
        return ResendWithConsoleSender()
    return ConsoleEmailSender()
