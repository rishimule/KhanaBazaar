# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Best-effort dispatch of account-status emails to Celery. Never raises into
the request path."""
import logging

logger = logging.getLogger(__name__)


def dispatch_account_status_email(user_id: int, event_key: str) -> None:
    """Enqueue the account-status email. Call AFTER session.commit()."""
    from app.worker import send_account_status_email_async

    try:
        send_account_status_email_async.delay(user_id, event_key)
    except Exception:  # noqa: BLE001 - best-effort; never block the request
        logger.exception(
            "Failed to enqueue account-status email for user_id=%s", user_id
        )
