"""Thin dispatcher around order-email Celery tasks.

Wraps `.delay()` so callers don't need to know which Celery task to fire and
broker/transport failures never bubble back into the request handler that
placed or updated an order. Logging surfaces drop reasons for ops debugging.
"""

import logging
from typing import Any

from app.worker import (
    send_order_confirmed_customer_async,
    send_order_placed_seller_async,
    send_order_status_changed_async,
)

logger = logging.getLogger(__name__)


def _safe_delay(task: Any, *args: Any) -> None:
    """Fire-and-forget Celery dispatch. Swallow and log any broker errors."""
    try:
        task.delay(*args)
    except Exception:  # noqa: BLE001 - intentional: never break the request path
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
