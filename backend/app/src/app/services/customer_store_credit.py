# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Customer store credit: money a seller owes a customer, spendable only with
that seller.

One cached balance on ``CustomerStoreCredit`` plus a ``CustomerStoreCreditEntry``
ledger (the source of truth). Every mutation writes a ledger row and adjusts the
cached balance in the same transaction. Services flush; callers commit.

This is the mirror image of ``services/credit.py`` (customer owes seller) and a
sibling of ``services/store_credit.py`` (platform owes seller). Do not conflate
the three: they answer three different questions.
"""
from typing import Optional

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.returns import (
    CustomerStoreCredit,
    CustomerStoreCreditEntry,
    StoreCreditEntryType,
)


class StoreCreditError(Exception):
    """Invalid customer-store-credit operation."""


async def get_or_create_account(
    session: AsyncSession, *, seller_profile_id: int, customer_profile_id: int
) -> CustomerStoreCredit:
    row = (
        await session.exec(
            select(CustomerStoreCredit).where(
                CustomerStoreCredit.seller_profile_id == seller_profile_id,
                CustomerStoreCredit.customer_profile_id == customer_profile_id,
            )
        )
    ).first()
    if row is None:
        row = CustomerStoreCredit(
            seller_profile_id=seller_profile_id,
            customer_profile_id=customer_profile_id,
        )
        session.add(row)
        await session.flush()
    return row


async def lock_account(
    session: AsyncSession, *, seller_profile_id: int, customer_profile_id: int
) -> Optional[CustomerStoreCredit]:
    """Row-lock an existing account so concurrent spends cannot lost-update the
    cached balance. Returns None when the pair has no account yet — a customer
    with no credit needs no lock."""
    return (
        await session.exec(
            select(CustomerStoreCredit)
            .where(
                CustomerStoreCredit.seller_profile_id == seller_profile_id,
                CustomerStoreCredit.customer_profile_id == customer_profile_id,
            )
            .with_for_update()
        )
    ).first()


async def _append(
    session: AsyncSession,
    account: CustomerStoreCredit,
    delta: float,
    entry_type: StoreCreditEntryType,
    *,
    return_request_id: Optional[int],
    order_id: Optional[int],
    note: Optional[str],
    actor_user_id: Optional[int],
) -> CustomerStoreCreditEntry:
    account.balance = round(account.balance + delta, 2)
    if account.balance < 0:
        raise StoreCreditError("negative_balance")
    entry = CustomerStoreCreditEntry(
        account_id=account.id,
        entry_type=entry_type,
        amount=round(delta, 2),
        balance_after=account.balance,
        return_request_id=return_request_id,
        order_id=order_id,
        note=note,
        actor_user_id=actor_user_id,
    )
    session.add(account)
    session.add(entry)
    await session.flush()
    return entry


async def grant(
    session: AsyncSession,
    account: CustomerStoreCredit,
    amount: float,
    *,
    entry_type: StoreCreditEntryType,
    return_request_id: Optional[int] = None,
    order_id: Optional[int] = None,
    note: Optional[str] = None,
    actor_user_id: Optional[int] = None,
) -> CustomerStoreCreditEntry:
    """Add `amount` to the customer's credit with this seller."""
    if amount <= 0:
        raise StoreCreditError("bad_amount")
    account.lifetime_earned = round(account.lifetime_earned + amount, 2)
    return await _append(
        session, account, amount, entry_type,
        return_request_id=return_request_id, order_id=order_id, note=note,
        actor_user_id=actor_user_id,
    )


async def spend(
    session: AsyncSession,
    account: CustomerStoreCredit,
    amount: float,
    *,
    order_id: int,
    actor_user_id: Optional[int] = None,
) -> float:
    """Spend up to `amount` against an order. Clamps to the available balance
    and returns what was actually applied (0.0 when there is nothing to spend)."""
    if amount <= 0:
        raise StoreCreditError("bad_amount")
    applied = round(min(amount, account.balance), 2)
    if applied <= 0:
        return 0.0
    account.lifetime_spent = round(account.lifetime_spent + applied, 2)
    await _append(
        session, account, -applied, StoreCreditEntryType.order_applied,
        return_request_id=None, order_id=order_id, note=None,
        actor_user_id=actor_user_id,
    )
    return applied


async def revert_order(
    session: AsyncSession,
    *,
    seller_profile_id: int,
    customer_profile_id: int,
    order_id: int,
    amount: float,
    actor_user_id: Optional[int] = None,
) -> None:
    """Give back credit spent on an order that was cancelled. No-op for a
    zero/negative amount or a pair that never had an account."""
    if amount <= 0:
        return
    account = await lock_account(
        session, seller_profile_id=seller_profile_id,
        customer_profile_id=customer_profile_id,
    )
    if account is None:
        return
    account.lifetime_spent = round(max(0.0, account.lifetime_spent - amount), 2)
    await _append(
        session, account, amount, StoreCreditEntryType.order_reverted,
        return_request_id=None, order_id=order_id,
        note=f"order #{order_id} cancelled", actor_user_id=actor_user_id,
    )


async def list_balances(
    session: AsyncSession, customer_profile_id: int
) -> list[CustomerStoreCredit]:
    return list(
        (
            await session.exec(
                select(CustomerStoreCredit)
                .where(CustomerStoreCredit.customer_profile_id == customer_profile_id)
                .order_by(col(CustomerStoreCredit.seller_profile_id))
            )
        ).all()
    )


async def list_entries(
    session: AsyncSession, account_id: int, *, limit: int = 50, offset: int = 0
) -> list[CustomerStoreCreditEntry]:
    return list(
        (
            await session.exec(
                select(CustomerStoreCreditEntry)
                .where(CustomerStoreCreditEntry.account_id == account_id)
                # id breaks ties: two entries written in one transaction can
                # share a created_at to the microsecond.
                .order_by(
                    col(CustomerStoreCreditEntry.created_at).desc(),
                    col(CustomerStoreCreditEntry.id).desc(),
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
