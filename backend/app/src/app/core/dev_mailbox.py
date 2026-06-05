# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Dev-only capture of outbound emails/SMS into the dev_email / dev_sms tables.

Best-effort: every function early-returns unless ENVIRONMENT == "development",
and any DB error is logged and swallowed so capture can NEVER block or break a
real send. Called from the console dispatch chokepoints (core/email.py,
core/sms.py, worker._resolve_email).
"""
import logging

from app.core.config import settings
from app.db import session as _db_session  # module ref so test engine override is honoured
from app.models.dev_email import DevEmail
from app.models.dev_sms import DevSms

logger = logging.getLogger(__name__)


async def record_outbound_email(
    *,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    reply_to: str | None = None,
    category: str | None = None,
    provider: str = "console",
) -> None:
    if settings.ENVIRONMENT != "development":
        return
    try:
        async with _db_session.async_session_factory() as s:
            s.add(
                DevEmail(
                    to_email=to,
                    subject=subject,
                    body_text=text,
                    body_html=html,
                    reply_to=reply_to,
                    category=category,
                    provider=provider,
                )
            )
            await s.commit()
    except Exception:  # noqa: BLE001 — capture must never break a send
        logger.exception("dev_mailbox: failed to record outbound email")


async def record_outbound_sms(
    *,
    to: str,
    text: str,
    category: str | None = None,
    provider: str = "console",
) -> None:
    if settings.ENVIRONMENT != "development":
        return
    try:
        async with _db_session.async_session_factory() as s:
            s.add(DevSms(to_phone=to, body=text, category=category, provider=provider))
            await s.commit()
    except Exception:  # noqa: BLE001
        logger.exception("dev_mailbox: failed to record outbound sms")
