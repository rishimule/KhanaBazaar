# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Thin dispatcher around the web-push Celery task (mirrors order_emails)."""
import logging

from kombu.exceptions import OperationalError as KombuOperationalError

from app.worker import send_order_push_async

logger = logging.getLogger(__name__)

_BROKER_ERRORS: tuple[type[BaseException], ...] = (
    KombuOperationalError,
    ConnectionError,
    OSError,
    TimeoutError,
)


def dispatch_notification_push(notification_id: int) -> None:
    """Fire-and-forget push dispatch; swallow + log broker outages."""
    try:
        send_order_push_async.delay(notification_id)
    except _BROKER_ERRORS:
        logger.exception(
            "Failed to dispatch push for notification_id=%s", notification_id
        )
