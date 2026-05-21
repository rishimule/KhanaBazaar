# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import json
import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Dev-only HTML previews are written here when html is non-empty in console
# mode. Empty string disables the preview. We gate the default on
# ``ENVIRONMENT == "development"`` so OTP plaintext does NOT leak to /tmp or
# logs in staging / prod (where ``EMAIL_PROVIDER=resend+console`` would
# otherwise mirror every email body to disk).
_DEV_PREVIEW_DIR = "/tmp" if settings.ENVIRONMENT == "development" else ""
_SUBJECT_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SUBJECT_SLUG_RE.sub("-", text.lower()).strip("-")[:60] or "email"


class EmailSender(Protocol):
    async def send(
        self,
        to: str,
        subject: str,
        *,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None: ...


class ConsoleEmailSender:
    async def send(
        self,
        to: str,
        subject: str,
        *,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        # Mirror the body to stdout / logs only in development. In other
        # environments, log subject + recipient metadata only — never the
        # body, which may contain OTP codes or order PII.
        if settings.ENVIRONMENT == "development":
            logger.info(
                "[EMAIL] to=%s reply_to=%s subject=%r\n%s",
                to,
                reply_to,
                subject,
                text,
            )
            print(f"[EMAIL] to={to}\n{text}")
        else:
            logger.info(
                "[EMAIL] to=%s reply_to=%s subject=%r (body suppressed)",
                to,
                reply_to,
                subject,
            )
        if html and _DEV_PREVIEW_DIR:
            try:
                path = Path(_DEV_PREVIEW_DIR) / (
                    f"khanabazaar_email_{_slug(subject)}_{int(time.time() * 1000)}.html"
                )
                path.write_text(html, encoding="utf-8")
                logger.info("[EMAIL] dev preview written: %s", path)
            except OSError as exc:
                logger.debug("dev preview write failed: %s", exc)


class ResendEmailSender:
    async def send(
        self,
        to: str,
        subject: str,
        *,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "text": text,
        }
        if html is not None:
            payload["html"] = html
        if reply_to is not None:
            payload["reply_to"] = reply_to
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                content=json.dumps(payload),
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()


class ResendWithConsoleSender:
    def __init__(self) -> None:
        self._console = ConsoleEmailSender()
        self._resend = ResendEmailSender()

    async def send(
        self,
        to: str,
        subject: str,
        *,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        await self._console.send(
            to, subject, text=text, html=html, reply_to=reply_to
        )
        try:
            await self._resend.send(
                to, subject, text=text, html=html, reply_to=reply_to
            )
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
