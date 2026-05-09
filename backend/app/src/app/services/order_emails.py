# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Thin dispatcher around order-email Celery tasks.

Wraps `.delay()` so callers don't need to know which Celery task to fire and
broker/transport failures never bubble back into the request handler that
placed or updated an order. Logging surfaces drop reasons for ops debugging.
"""

import logging
from typing import Any

from kombu.exceptions import OperationalError as KombuOperationalError

from app.worker import (
    send_order_confirmed_customer_async,
    send_order_placed_seller_async,
    send_order_status_changed_async,
)

logger = logging.getLogger(__name__)

# Catch only broker/transport errors. Programming errors (TypeError on the
# wrong arg shape, AttributeError, etc.) should crash loud during dev so they
# surface in tests rather than getting silently logged in prod.
_BROKER_ERRORS: tuple[type[BaseException], ...] = (
    KombuOperationalError,
    ConnectionError,
    OSError,
    TimeoutError,
)


def _safe_delay(task: Any, *args: Any) -> None:
    """Fire-and-forget Celery dispatch. Swallow and log broker outages so a
    Redis hiccup never breaks the request path that placed or updated an order."""
    try:
        task.delay(*args)
    except _BROKER_ERRORS:
        logger.exception(
            "Failed to dispatch order email task=%s args=%s",
            getattr(task, "name", repr(task)),
            args,
        )


def dispatch_order_placed(order_ids: list[int]) -> None:
    """Notify the customer (one summary email) and each seller (one per order)."""
    if not order_ids:
        return
    _safe_delay(send_order_confirmed_customer_async, order_ids)
    for oid in order_ids:
        _safe_delay(send_order_placed_seller_async, oid)


def dispatch_order_status_changed(
    order_id: int, new_status: str, *, notify_seller: bool = False
) -> None:
    """Notify the customer (always) and optionally the seller of a status change."""
    _safe_delay(send_order_status_changed_async, order_id, new_status, "customer")
    if notify_seller:
        _safe_delay(send_order_status_changed_async, order_id, new_status, "seller")
