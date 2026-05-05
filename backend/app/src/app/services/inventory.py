from typing import Iterable

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Category, MasterProduct, Subcategory
from app.models.profile import SellerProfileService
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


async def assert_products_in_seller_services(
    session: AsyncSession,
    seller_profile_id: int,
    product_ids: Iterable[int],
) -> None:
    """Raise 403 SERVICE_NOT_APPROVED if any product belongs to a service
    not in the seller's approved set."""
    ids = list(set(product_ids))
    if not ids:
        return

    approved_result = await session.exec(
        select(SellerProfileService.service_id).where(
            SellerProfileService.seller_profile_id == seller_profile_id
        )
    )
    approved = set(approved_result.all())

    stmt = (
        select(MasterProduct.id, Category.service_id)
        .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
        .join(Category, Category.id == Subcategory.category_id)  # type: ignore[arg-type]
        .where(MasterProduct.id.in_(ids))  # type: ignore[union-attr]
    )
    rows = await session.exec(stmt)
    by_product = dict(rows.all())

    missing = [pid for pid in ids if pid not in by_product]
    if missing:
        raise HTTPException(
            status_code=404,
            detail={"code": "PRODUCT_NOT_FOUND", "product_ids": missing},
        )

    forbidden = [pid for pid, sid in by_product.items() if sid not in approved]
    if forbidden:
        raise HTTPException(
            status_code=403,
            detail={"code": "SERVICE_NOT_APPROVED", "product_ids": forbidden},
        )
