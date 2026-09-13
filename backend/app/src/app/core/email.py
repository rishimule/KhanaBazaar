# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import json
import logging
import re
import time
from email.message import EmailMessage
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import aiosmtplib
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Dev-only HTML previews are written to ``settings.EMAIL_DEV_PREVIEW_DIR`` when
# html is non-empty in console mode. Empty (the default everywhere) disables it.
#
# This is read live rather than snapshotted at import so tests can monkeypatch
# it. It is deliberately NOT derived from ``ENVIRONMENT``: the GCP deployment
# runs ENVIRONMENT=development so the dev mailbox works, so an ENVIRONMENT gate
# mirrored every HTML body — OTP codes included — into the Cloud Run container's
# in-memory /tmp, for the life of the revision. /dev-emails renders the same
# HTML, so the files are only worth having when you explicitly ask for them.
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
    def __init__(self, record_provider: str = "console") -> None:
        self._record_provider = record_provider

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
        preview_dir = settings.EMAIL_DEV_PREVIEW_DIR
        if html and preview_dir:
            try:
                path = Path(preview_dir) / (
                    f"khanabazaar_email_{_slug(subject)}_{int(time.time() * 1000)}.html"
                )
                path.write_text(html, encoding="utf-8")
                logger.info("[EMAIL] dev preview written: %s", path)
            except OSError as exc:
                logger.debug("dev preview write failed: %s", exc)
        # Dev-only capture into the dev_email table (best-effort).
        from app.core.dev_mailbox import record_outbound_email

        await record_outbound_email(
            to=to,
            subject=subject,
            text=text,
            html=html,
            reply_to=reply_to,
            provider=self._record_provider,
        )


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


class BrevoEmailSender:
    """Brevo transactional email over its HTTP API.

    Not a subclass of / delegate to ResendEmailSender: Brevo authenticates with
    an ``api-key`` header rather than ``Authorization: Bearer``, and its payload
    keys differ throughout (``sender``/``textContent``/``htmlContent``/``replyTo``
    vs Resend's ``from``/``text``/``html``/``reply_to``).
    """

    ENDPOINT = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, timeout: float = 5.0) -> None:
        # 5s default, vs the 3s used for Resend: Brevo's API is EU-hosted and
        # the api service runs in asia-south1, so a cold TLS handshake eats a
        # chunk of the budget. The API path runs on the OTP request path, so it
        # stays bounded; the Celery worker passes a longer one.
        self._timeout = timeout
        if not (settings.BREVO_API_KEY and settings.BREVO_FROM_EMAIL):
            logger.warning(
                "[EMAIL] Brevo provider selected but BREVO_API_KEY/"
                "BREVO_FROM_EMAIL are not both configured; sends will fail."
            )

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
            "sender": {
                "name": settings.EMAIL_BRAND_NAME,
                "email": settings.BREVO_FROM_EMAIL,
            },
            "to": [{"email": to}],
            "subject": subject,
            "textContent": text,
        }
        if html is not None:
            payload["htmlContent"] = html
        if reply_to is not None:
            payload["replyTo"] = {"email": reply_to}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self.ENDPOINT,
                content=json.dumps(payload),
                headers={
                    "api-key": settings.BREVO_API_KEY,
                    "content-type": "application/json",
                    "accept": "application/json",
                },
            )
            response.raise_for_status()


class SmtpEmailSender:
    def __init__(self) -> None:
        if not (
            settings.SMTP_HOST and settings.SMTP_USERNAME and settings.SMTP_PASSWORD
        ):
            logger.warning(
                "[EMAIL] SMTP provider selected but SMTP_HOST/SMTP_USERNAME/"
                "SMTP_PASSWORD are not all configured; sends will fail."
            )

    async def send(
        self,
        to: str,
        subject: str,
        *,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        msg = EmailMessage()
        msg["From"] = f"{settings.EMAIL_BRAND_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg["To"] = to
        msg["Subject"] = subject
        if reply_to is not None:
            msg["Reply-To"] = reply_to
        msg.set_content(text)
        if html is not None:
            msg.add_alternative(html, subtype="html")
        # start_tls (STARTTLS, port 587) and use_tls (implicit SSL, port 465)
        # are mutually exclusive — deriving both from one bool guarantees that.
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            start_tls=not settings.SMTP_USE_TLS,
            use_tls=settings.SMTP_USE_TLS,
            timeout=settings.SMTP_TIMEOUT,
        )


class SmtpWithConsoleSender:
    def __init__(self) -> None:
        self._console = ConsoleEmailSender(record_provider="smtp")
        self._smtp = SmtpEmailSender()

    async def send(
        self,
        to: str,
        subject: str,
        *,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        # Console first: the dev-mailbox row is written regardless of whether the
        # real Gmail send succeeds, so /dev-emails never loses a record.
        await self._console.send(
            to, subject, text=text, html=html, reply_to=reply_to
        )
        try:
            await self._smtp.send(
                to, subject, text=text, html=html, reply_to=reply_to
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            # OSError covers ssl.SSLError (STARTTLS handshake failures on 587,
            # which aiosmtplib does NOT wrap into SMTPException), socket.gaierror,
            # ConnectionError, and TimeoutError. The dev-mailbox row is already
            # written, so a Gmail-side failure never breaks the calling flow.
            logger.warning(
                "[EMAIL] SMTP send failed to=%s error=%s "
                "(console capture already recorded)",
                to,
                exc,
            )


class ResendWithConsoleSender:
    def __init__(self) -> None:
        self._console = ConsoleEmailSender(record_provider="resend")
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


class BrevoWithConsoleSender:
    def __init__(self) -> None:
        self._console = ConsoleEmailSender(record_provider="brevo")
        self._brevo = BrevoEmailSender()

    async def send(
        self,
        to: str,
        subject: str,
        *,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        # Console first: the dev-mailbox row is written regardless of whether the
        # real Brevo send succeeds, so /dev-emails never loses a record.
        await self._console.send(to, subject, text=text, html=html, reply_to=reply_to)
        try:
            await self._brevo.send(
                to, subject, text=text, html=html, reply_to=reply_to
            )
        except httpx.HTTPError as exc:
            # Wider than ResendWithConsoleSender's HTTPStatusError on purpose:
            # httpx.HTTPError also covers connect/read timeouts and DNS failures,
            # so a Brevo outage degrades this deployment to console-only capture
            # instead of breaking OTP login.
            logger.warning(
                "[EMAIL] Brevo send failed to=%s error=%r "
                "(console capture already recorded)",
                to,
                exc,
            )


@lru_cache(maxsize=1)
def get_email_sender() -> EmailSender:
    if settings.EMAIL_PROVIDER == "resend":
        return ResendEmailSender()
    if settings.EMAIL_PROVIDER == "resend+console":
        return ResendWithConsoleSender()
    if settings.EMAIL_PROVIDER == "brevo":
        return BrevoEmailSender()
    if settings.EMAIL_PROVIDER == "brevo+console":
        return BrevoWithConsoleSender()
    if settings.EMAIL_PROVIDER == "smtp":
        return SmtpEmailSender()
    if settings.EMAIL_PROVIDER == "smtp+console":
        return SmtpWithConsoleSender()
    return ConsoleEmailSender()
