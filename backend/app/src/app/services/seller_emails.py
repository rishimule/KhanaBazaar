# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Thin dispatcher around seller-verification email Celery tasks.

Mirrors `order_emails.py`: wraps `.delay()` so callers don't need to know which
task to fire and broker/transport failures never bubble back into the request
handler that approved or rejected a seller application.
"""

import logging
from typing import Any

from kombu.exceptions import OperationalError as KombuOperationalError

from app.worker import (
    send_customer_welcome_async,
    send_seller_application_submitted_async,
    send_seller_approved_async,
    send_seller_rejected_async,
)

logger = logging.getLogger(__name__)

_BROKER_ERRORS: tuple[type[BaseException], ...] = (
    KombuOperationalError,
    ConnectionError,
    OSError,
    TimeoutError,
)


def _safe_delay(task: Any, *args: Any) -> None:
    """Fire-and-forget Celery dispatch. Swallow and log broker outages so a
    Redis hiccup never breaks the admin verify request path."""
    try:
        task.delay(*args)
    except _BROKER_ERRORS:
        logger.exception(
            "Failed to dispatch seller email task=%s args=%s",
            getattr(task, "name", repr(task)),
            args,
        )


def dispatch_seller_approved(to_email: str, business_name: str) -> None:
    if not to_email:
        return
    _safe_delay(send_seller_approved_async, to_email, business_name)


def dispatch_seller_rejected(
    to_email: str, business_name: str, reason: str
) -> None:
    if not to_email:
        return
    _safe_delay(send_seller_rejected_async, to_email, business_name, reason)


def dispatch_seller_application_submitted(seller_profile_id: int) -> None:
    """Notify the support inbox of a new (or resubmitted) seller application."""
    _safe_delay(send_seller_application_submitted_async, seller_profile_id)


def dispatch_customer_welcome(user_id: int) -> None:
    """Greet a newly-registered customer."""
    _safe_delay(send_customer_welcome_async, user_id)
