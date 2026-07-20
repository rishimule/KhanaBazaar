# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Account state-machine funnel: every deactivate/suspend/delete/restore/
reactivate transition goes through ``transition()``.

Soft-delete only — no row is hard-deleted, no PII is scrubbed.
"""
from datetime import datetime, timezone

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import AccountStatus, User
from app.models.commerce import Order, OrderStatus
from app.models.credit import CreditAccount
from app.models.customer_account_event import CustomerAccountEvent
from app.models.profile import CustomerProfile
from app.services.sessions import revoke_all_sessions

TERMINAL_ORDER_STATUSES: set[OrderStatus] = {
    OrderStatus.Delivered,
    OrderStatus.Cancelled,
}

# The only legal (from, to) pairs. Anything else raises InvalidTransition.
_LEGAL_TRANSITIONS: set[tuple[AccountStatus, AccountStatus]] = {
    (AccountStatus.active, AccountStatus.deactivated),
    (AccountStatus.deactivated, AccountStatus.active),
    (AccountStatus.active, AccountStatus.suspended),
    (AccountStatus.suspended, AccountStatus.active),
    (AccountStatus.active, AccountStatus.deleted),
    (AccountStatus.deactivated, AccountStatus.deleted),
    (AccountStatus.suspended, AccountStatus.deleted),
    (AccountStatus.deleted, AccountStatus.active),
}


class AccountLifecycleError(Exception):
    """Base for lifecycle errors."""


class UserNotFound(AccountLifecycleError):
    pass


class InvalidTransition(AccountLifecycleError):
    def __init__(self, from_status: AccountStatus, to_status: AccountStatus) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"illegal transition {from_status.value} -> {to_status.value}"
        )


class OpenObligations(AccountLifecycleError):
    def __init__(self, open_orders: int, credit_accounts: int) -> None:
        self.open_orders = open_orders
        self.credit_accounts = credit_accounts
        super().__init__(
            f"open obligations: {open_orders} orders, {credit_accounts} credit accounts"
        )


async def has_open_obligations(
    session: AsyncSession, customer_profile_id: int
) -> tuple[int, int]:
    """Return (non-terminal order count, credit accounts with outstanding_balance>0)."""
    order_count = (
        await session.exec(
            select(func.count())
            .select_from(Order)
            .where(
                Order.customer_profile_id == customer_profile_id,
                Order.status.notin_(TERMINAL_ORDER_STATUSES),  # type: ignore[attr-defined]
            )
        )
    ).one()
    credit_count = (
        await session.exec(
            select(func.count())
            .select_from(CreditAccount)
            .where(
                CreditAccount.customer_profile_id == customer_profile_id,
                CreditAccount.outstanding_balance > 0,
            )
        )
    ).one()
    return int(order_count), int(credit_count)


async def transition(
    session: AsyncSession,
    *,
    user_id: int,
    to_status: AccountStatus,
    actor_user_id: int | None,
    actor_role: str,
    reason: str | None,
    enforce_obligations: bool,
) -> User:
    """Move a user to ``to_status``. Row-locked; flushes; the caller commits.

    Raises UserNotFound / InvalidTransition / OpenObligations.
    """
    user = (
        await session.exec(select(User).where(User.id == user_id).with_for_update())
    ).first()
    if user is None:
        raise UserNotFound(str(user_id))

    from_status = user.account_status
    if (from_status, to_status) not in _LEGAL_TRANSITIONS:
        raise InvalidTransition(from_status, to_status)

    if enforce_obligations and to_status in (
        AccountStatus.deactivated,
        AccountStatus.deleted,
    ):
        profile = (
            await session.exec(
                select(CustomerProfile).where(CustomerProfile.user_id == user_id)
            )
        ).first()
        if profile is not None and profile.id is not None:
            open_orders, credit_accounts = await has_open_obligations(
                session, profile.id
            )
            if open_orders or credit_accounts:
                raise OpenObligations(open_orders, credit_accounts)

    user.account_status = to_status
    user.is_active = to_status == AccountStatus.active
    user.status_changed_at = datetime.now(timezone.utc)
    user.status_reason = reason
    user.status_changed_by_user_id = actor_user_id
    session.add(user)

    session.add(
        CustomerAccountEvent(
            user_id=user_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
        )
    )

    if to_status != AccountStatus.active:
        await revoke_all_sessions(session, user_id=user_id)

    await session.flush()
    return user
