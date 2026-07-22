# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Compose + record in-app seller notifications for fee lifecycle events.

English-only copy (matches the customer notification convention). Best-effort:
resolves the store's seller and returns silently if unresolved. Records via
record_seller_notification (flush; caller commits). Phone/email channels are
layered in Plan 3c-ii's follow-up."""
from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import NotificationType
from app.models.store import Store
from app.services.notifications import record_seller_notification

# (title, status_value, body-template) per fee notification type. `{until}` is
# substituted with the validity date when provided (else a generic clause).
_COPY: dict[NotificationType, tuple[str, str, str]] = {
    NotificationType.FeeActivated: (
        "Subscription active", "active",
        "Your subscription is active{until}.",
    ),
    NotificationType.FeeExpiring: (
        "Plan expiring soon", "expiring",
        "Your plan expires{until}. Renew to keep your store active.",
    ),
    NotificationType.FeeSuspended: (
        "Store service suspended", "suspended",
        "A service on your store has been suspended. Renew or clear your balance to reactivate it.",
    ),
    NotificationType.FeeLowBalance: (
        "Low balance", "low_balance",
        "Your pay-per-order balance is running low. Top up to avoid interruption.",
    ),
    NotificationType.FeeReactivated: (
        "Store service reactivated", "reactivated",
        "Your service is active again. Thanks for topping up.",
    ),
}


async def notify_seller_fee_event(
    session: AsyncSession,
    *,
    store_id: int,
    type: NotificationType,  # noqa: A002 - matches the model field name
    valid_until: date | None = None,
) -> int | None:
    """Record an in-app seller notification for a fee event. No-op (returns
    None) if the store or its seller can't be resolved. On success, returns
    the resolved seller_profile_id so sweep-driven callers can fan out to
    other channels post-commit. Caller commits."""
    copy = _COPY.get(type)
    if copy is None:
        return None
    seller_profile_id = (
        await session.exec(
            select(Store.seller_profile_id).where(Store.id == store_id)
        )
    ).first()
    if seller_profile_id is None:
        return None
    title, status_value, body_tmpl = copy
    until_clause = f" until {valid_until.isoformat()}" if valid_until else ""
    if type is NotificationType.FeeExpiring:
        until_clause = f" on {valid_until.isoformat()}" if valid_until else " soon"
    body = body_tmpl.format(until=until_clause)
    await record_seller_notification(
        session,
        seller_profile_id=seller_profile_id,
        type=type,
        title=title,
        body=body,
        status_value=status_value,
    )
    return seller_profile_id
