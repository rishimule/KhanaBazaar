from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_seller
from app.db.session import get_db_session
from app.models.base import User
from app.models.catalog import MasterProduct
from app.models.store import Store, StoreInventory

router = APIRouter()

# -------------------------------------------------------------
# Stores API
# -------------------------------------------------------------

@router.get("/", response_model=List[Store])
async def list_stores(
    skip: int = 0, limit: int = 100,
    session: AsyncSession = Depends(get_db_session)
) -> List[Store]:
    # Returns all active stores
    result = await session.exec(select(Store).where(Store.is_active).offset(skip).limit(limit))
    return list(result.all())

@router.post("/", response_model=Store)
async def create_store(
    store: Store,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller)
) -> Store:
    store.id = None
    assert seller.id is not None, "Seller ID cannot be None"
    store.seller_id = seller.id  # Force the store to belong to the authenticated seller

    session.add(store)
    await session.commit()
    await session.refresh(store)
    return store

@router.get("/{store_id}", response_model=Store)
async def get_store(store_id: int, session: AsyncSession = Depends(get_db_session)) -> Store:
    store = await session.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


# -------------------------------------------------------------
# Inventory API
# -------------------------------------------------------------

@router.get("/{store_id}/inventory", response_model=List[StoreInventory])
async def list_store_inventory(
    store_id: int,
    session: AsyncSession = Depends(get_db_session)
) -> List[StoreInventory]:
    # Verify store exists
    store = await session.get(Store, store_id)
    if not store or not store.is_active:
        raise HTTPException(status_code=404, detail="Store not found or inactive")

    result = await session.exec(
        select(StoreInventory).where(StoreInventory.store_id == store_id, StoreInventory.is_available)
    )
    return list(result.all())

@router.post("/{store_id}/inventory", response_model=StoreInventory)
async def add_inventory(
    store_id: int,
    inventory: StoreInventory,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller)
) -> StoreInventory:
    # 1. Verify the seller owns the store
    store = await session.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    if store.seller_id != seller.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this store")

    # 2. Verify the master product exists
    product = await session.get(MasterProduct, inventory.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Master product not found")

    # 3. Check for duplicates (handled by DB UniqueConstraint, but good to check nicely)
    check_stmt = select(StoreInventory).where(
        StoreInventory.store_id == store_id,
        StoreInventory.product_id == inventory.product_id
    )
    existing = await session.exec(check_stmt)
    if existing.first():
         raise HTTPException(status_code=400, detail="Product already exists in store inventory. Use PUT to update.")

    inventory.id = None
    inventory.store_id = store_id
    session.add(inventory)
    await session.commit()
    await session.refresh(inventory)
    return inventory
