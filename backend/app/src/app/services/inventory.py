from typing import Iterable

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.store import StoreInventory


async def lock_inventory_rows(
    session: AsyncSession, inventory_ids: Iterable[int]
) -> list[StoreInventory]:
    """Acquire per-row locks on inventory rows in deterministic id order
    to avoid deadlocks under concurrent checkout. SQLAlchemy emits the
    ORDER BY before FOR UPDATE; the deterministic order makes interleaved
    transactions queue rather than deadlock."""
    ids = sorted(set(inventory_ids))
    if not ids:
        return []
    stmt = (
        select(StoreInventory)
        .where(StoreInventory.id.in_(ids))  # type: ignore[union-attr]
        .order_by(StoreInventory.id)  # type: ignore[arg-type]
        .with_for_update()
    )
    result = await session.exec(stmt)
    return list(result.all())


def decrement_stock(inv: StoreInventory, quantity: int) -> None:
    """Mutate the *already-locked* inventory instance. Caller must have
    obtained `inv` via `lock_inventory_rows()` in the current session so
    the unit-of-work flushes the change while the row lock is still held."""
    if quantity < 0:
        raise ValueError("quantity must be non-negative")
    inv.stock -= quantity


def restock(inv: StoreInventory, quantity: int) -> None:
    if quantity < 0:
        raise ValueError("quantity must be non-negative")
    inv.stock += quantity
