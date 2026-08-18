# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Thin dispatcher around return-comms Celery tasks.

Mirrors `services/order_emails.py`: broker outages are logged, never raised
into the request path that created or advanced a return.
"""
import logging
from typing import Any

from kombu.exceptions import OperationalError as KombuOperationalError

from app.worker import send_return_otp_email_async, send_return_otp_phone_async

logger = logging.getLogger(__name__)

# Catch only broker/transport errors. Programming errors should crash loud in
# dev rather than being silently logged in prod.
_BROKER_ERRORS: tuple[type[BaseException], ...] = (
    KombuOperationalError,
    ConnectionError,
    OSError,
    TimeoutError,
)


def _safe_delay(task: Any, *args: Any) -> None:
    try:
        task.delay(*args)
    except _BROKER_ERRORS:
        logger.exception(
            "Failed to dispatch return comms task=%s args=%s",
            getattr(task, "name", repr(task)),
            args,
        )


def dispatch_return_otp(user_id: int, return_id: int, code: str, purpose: str) -> None:
    """Send a return confirmation code by email and phone. `purpose` is
    'initiate' or 'payment'."""
    _safe_delay(send_return_otp_email_async, user_id, return_id, code, purpose)
    _safe_delay(send_return_otp_phone_async, user_id, return_id, code, purpose)
