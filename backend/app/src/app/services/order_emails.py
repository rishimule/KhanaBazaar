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
    send_admin_order_action_customer_async,
    send_admin_order_action_seller_async,
    send_delivery_otp_email_async,
    send_delivery_otp_sms_async,
    send_order_confirmed_customer_async,
    send_order_placed_seller_async,
    send_order_review_request_async,
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


def dispatch_delivery_otp(order_id: int, code: str) -> None:
    """Fire the email + SMS handover-code tasks (in-app is recorded separately)."""
    _safe_delay(send_delivery_otp_email_async, order_id, code)
    _safe_delay(send_delivery_otp_sms_async, order_id, code)


_CUSTOMER_NOTIFY_ACTIONS = frozenset(
    {"order.rewind", "order.refund", "order.cancel", "order.address_override"}
)


def dispatch_admin_order_action(order_id: int, action: str, reason: str) -> None:
    """Notify the seller (always) and the customer for impactful admin actions."""
    _safe_delay(send_admin_order_action_seller_async, order_id, action, reason)
    if action in _CUSTOMER_NOTIFY_ACTIONS:
        _safe_delay(
            send_admin_order_action_customer_async, order_id, action, reason
        )


def dispatch_order_status_changed(
    order_id: int,
    new_status: str,
    *,
    notify_seller: bool = False,
    reason: str | None = None,
) -> None:
    """Notify the customer (always) and optionally the seller of a status change.

    When ``new_status == "delivered"``, also schedule the post-delivery
    review-request email for 24h later.
    """
    _safe_delay(
        send_order_status_changed_async, order_id, new_status, "customer", reason
    )
    if notify_seller:
        _safe_delay(
            send_order_status_changed_async, order_id, new_status, "seller", reason
        )
    if new_status == "delivered":
        try:
            send_order_review_request_async.apply_async(
                args=[order_id], countdown=86400
            )
        except _BROKER_ERRORS:
            logger.exception(
                "Failed to schedule order_review_request for order_id=%s", order_id
            )
