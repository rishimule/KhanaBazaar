# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Store-level wallet credit: platform-held money owed back to the seller.

One cached balance on Store.fee_credit_balance + a StoreCreditEvent ledger
(source of truth). Every mutation writes a ledger row and adjusts the cached
balance in the same transaction. Services flush; callers commit."""
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform_fee import StoreCreditEvent, StoreCreditReason
from app.models.store import Store


class StoreCreditError(Exception):
    """Invalid wallet-credit operation."""


async def load_store(session: AsyncSession, store_id: int) -> Store:
    store = await session.get(Store, store_id)
    if store is None:
        raise StoreCreditError("store_not_found")
    return store


async def _record(
    session: AsyncSession, store: Store, delta: float, reason: StoreCreditReason,
    *, actor: str, note: Optional[str], related_arrangement_id: Optional[int],
    related_payment_id: Optional[int],
) -> None:
    # Row-lock the store to serialise concurrent wallet mutations (opt-in with
    # credit, apply-credit, admin ops) so the cached balance can't lost-update.
    await session.exec(
        select(Store).where(Store.id == store.id).with_for_update()
    )
    store.fee_credit_balance = round(store.fee_credit_balance + delta, 2)
    session.add(store)
    session.add(
        StoreCreditEvent(
            store_id=store.id, amount_delta=delta, reason=reason, actor=actor,
            note=note, related_arrangement_id=related_arrangement_id,
            related_payment_id=related_payment_id,
        )
    )
    await session.flush()


async def grant(
    session: AsyncSession, store: Store, amount: float, *, actor: str,
    note: Optional[str] = None, reason: StoreCreditReason = StoreCreditReason.AdminAdjust,
    related_arrangement_id: Optional[int] = None,
    related_payment_id: Optional[int] = None,
) -> None:
    """Add `amount` (signed) to the store's credit. Rejects a result below zero
    (store wallet credit is always ≥ 0 — arrangement debt lives on
    FeeArrangement.balance, not here). Used for admin grant/adjust + exit-grant."""
    if amount == 0:
        raise StoreCreditError("zero_amount")
    if store.fee_credit_balance + amount < 0:
        raise StoreCreditError("negative_balance")
    await _record(
        session, store, amount, reason, actor=actor, note=note,
        related_arrangement_id=related_arrangement_id,
        related_payment_id=related_payment_id,
    )


async def apply(
    session: AsyncSession, store: Store, amount: float, *, actor: str,
    note: Optional[str] = None, related_arrangement_id: Optional[int] = None,
    related_payment_id: Optional[int] = None,
) -> float:
    """Spend up to `amount` of credit toward an obligation. Clamps to the
    available balance and returns the amount actually applied."""
    if amount <= 0:
        raise StoreCreditError("bad_amount")
    applied = round(min(amount, store.fee_credit_balance), 2)
    if applied <= 0:
        return 0.0
    await _record(
        session, store, -applied, StoreCreditReason.AppliedToFee, actor=actor,
        note=note, related_arrangement_id=related_arrangement_id,
        related_payment_id=related_payment_id,
    )
    return applied


async def cash_out(
    session: AsyncSession, store: Store, amount: float, *, actor: str, note: str
) -> None:
    """Admin issues a real (offline) refund of `amount` of unused credit."""
    if amount <= 0 or amount > store.fee_credit_balance:
        raise StoreCreditError("bad_amount")
    await _record(
        session, store, -amount, StoreCreditReason.AdminCashOut, actor=actor,
        note=note, related_arrangement_id=None, related_payment_id=None,
    )
