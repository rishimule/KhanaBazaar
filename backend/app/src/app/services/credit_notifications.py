# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Best-effort credit notifications (in-app). English-only copy, consistent
with the rest of the notification system. Every dispatcher is post-commit and
swallows errors so it can never roll back or block a charge/grant."""
import logging
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Order
from app.models.credit import CreditAccount
from app.models.notification import Notification, NotificationType
from app.models.store import Store

logger = logging.getLogger(__name__)

_BANDS = (80, 90, 100)


async def _record(
    session: AsyncSession,
    *,
    status_value: str,
    title: str,
    body: str,
    customer_profile_id: Optional[int] = None,
    seller_profile_id: Optional[int] = None,
) -> None:
    session.add(
        Notification(
            customer_profile_id=customer_profile_id,
            seller_profile_id=seller_profile_id,
            type=NotificationType.Credit,
            title=title,
            body=body,
            status_value=status_value,
        )
    )


async def notify_credit_granted(session: AsyncSession, account: CreditAccount) -> None:
    """Tell the customer they've been granted credit at the seller's store."""
    try:
        store_name = (
            await session.exec(
                select(Store.name).where(
                    Store.seller_profile_id == account.seller_profile_id
                )
            )
        ).first() or "a store"
        await _record(
            session,
            customer_profile_id=account.customer_profile_id,
            status_value="granted",
            title="Credit available",
            body=(
                f"You can now pay on credit at {store_name} "
                f"(limit ₹{account.credit_limit:.0f})."
            ),
        )
        await session.commit()
    except Exception:
        logger.exception("credit_grant_notify_failed account_id=%s", account.id)


async def record_and_dispatch_credit_charge_notifications(
    session: AsyncSession, order: Order
) -> None:
    """After a credit charge: usage-threshold alerts (seller + customer) when a
    new 80/90/100% band is crossed, plus a per-transaction balance update to the
    customer. Best-effort, post-commit."""
    try:
        seller_id = (
            await session.exec(
                select(Store.seller_profile_id).where(Store.id == order.store_id)
            )
        ).first()
        if seller_id is None:
            return
        acct = (
            await session.exec(
                select(CreditAccount).where(
                    CreditAccount.seller_profile_id == seller_id,
                    CreditAccount.customer_profile_id == order.customer_profile_id,
                )
            )
        ).first()
        if acct is None or acct.credit_limit <= 0:
            return

        pct = (acct.outstanding_balance / acct.credit_limit) * 100.0
        crossed = 0
        for band in _BANDS:
            if pct >= band and band > acct.last_notified_threshold:
                crossed = band
        if crossed:
            acct.last_notified_threshold = crossed
            session.add(acct)
            await _record(
                session,
                seller_profile_id=seller_id,
                status_value="threshold",
                title="Customer credit threshold reached",
                body=f"A credit customer has used {crossed}% of their credit limit.",
            )
            await _record(
                session,
                customer_profile_id=order.customer_profile_id,
                status_value="threshold",
                title="Credit usage alert",
                body=f"You have used {crossed}% of your credit limit.",
            )
        elif pct < acct.last_notified_threshold:
            # Usage dropped below the last-notified band (e.g. after a repayment);
            # recompute the current band so the next crossing re-fires.
            new_band = 0
            for band in _BANDS:
                if pct >= band:
                    new_band = band
            acct.last_notified_threshold = new_band
            session.add(acct)

        available = round(acct.credit_limit - acct.outstanding_balance, 2)
        await _record(
            session,
            customer_profile_id=order.customer_profile_id,
            status_value="balance",
            title=f"Credit charged for order #{order.id}",
            body=(
                f"Outstanding ₹{acct.outstanding_balance:.2f}, "
                f"available ₹{available:.2f}."
            ),
        )
        await session.commit()
    except Exception:
        logger.exception("credit_charge_notify_failed order_id=%s", order.id)
