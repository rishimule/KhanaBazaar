# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Dev-only capture of outbound emails/SMS into the dev_email / dev_sms tables.

Best-effort: every function early-returns unless ENVIRONMENT == "development",
and any DB error is logged and swallowed so capture can NEVER block or break a
real send. Called from the console dispatch chokepoints (core/email.py,
core/sms.py, worker._resolve_email).

Each capture opens a short-lived engine bound to the *current* event loop and
disposes it in a finally — mirroring worker._load_order_email_context. The
worker path runs this inside a fresh `asyncio.run` loop per task (Celery
prefork), so reusing the app's shared pooled engine would hand back a
connection bound to a now-closed loop. The engine URL is read from
app.db.session.engine at call time so the test-suite's engine override (and its
test DB) is honoured.
"""
import logging

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.db import (
    session as _db_session,  # module ref so the test engine override is honoured
)
from app.models.base import BaseSchema
from app.models.dev_email import DevEmail
from app.models.dev_sms import DevSms
from app.models.dev_whatsapp import DevWhatsApp

logger = logging.getLogger(__name__)


async def _persist(instance: BaseSchema) -> None:
    """Insert one row on a fresh, immediately-disposed engine (loop-safe)."""
    if settings.ENVIRONMENT != "development":
        return
    try:
        engine = create_async_engine(_db_session.engine.url)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as s:
                s.add(instance)
                await s.commit()
        finally:
            await engine.dispose()
    except Exception:  # noqa: BLE001 — capture must never break a send
        logger.exception(
            "dev_mailbox: failed to record %s", type(instance).__name__
        )


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
    await _persist(
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


async def record_outbound_sms(
    *,
    to: str,
    text: str,
    category: str | None = None,
    provider: str = "console",
) -> None:
    await _persist(DevSms(to_phone=to, body=text, category=category, provider=provider))


async def record_outbound_whatsapp(
    *,
    to: str,
    body: str,
    template: str | None = None,
    category: str | None = None,
    provider: str = "console",
) -> None:
    await _persist(
        DevWhatsApp(
            to_phone=to,
            body=body,
            template=template,
            category=category,
            provider=provider,
        )
    )
