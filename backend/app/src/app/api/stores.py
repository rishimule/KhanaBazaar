from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_seller
from app.db.session import get_db_session
from app.models.base import User, UserRole
from app.models.catalog import MasterProduct
from app.models.seller import SellerProfile, VerificationStatus
from app.models.store import Store, StoreInventory
from app.schemas.address import address_from_payload, address_to_payload
from app.schemas.stores import StoreCreate, StoreRead

router = APIRouter()

# -------------------------------------------------------------
# Stores API
# -------------------------------------------------------------


def _store_read(store: Store) -> StoreRead:
    assert store.id is not None
    return StoreRead(
        id=store.id,
        name=store.name,
        address=address_to_payload(store),
        is_active=store.is_active,
        seller_id=store.seller_id,
        created_at=store.created_at.isoformat(),
        updated_at=store.updated_at.isoformat(),
    )


async def _get_approved_store_or_404(
    store_id: int, session: AsyncSession
) -> Store:
    """Return an active store whose owning seller is Approved, or 404."""
    stmt = (
        select(Store)
        .join(SellerProfile, SellerProfile.user_id == Store.seller_id)
        .where(
            Store.id == store_id,
            Store.is_active,
            SellerProfile.verification_status == VerificationStatus.Approved,
        )
    )
    result = await session.exec(stmt)
    store = result.first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


@router.get("/", response_model=List[StoreRead])
async def list_stores(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
) -> List[StoreRead]:
    result = await session.exec(
        select(Store).where(Store.is_active).offset(skip).limit(limit)
    )
    return [_store_read(store) for store in result.all()]


@router.get("/my", response_model=List[StoreRead])
async def list_my_stores(
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> List[StoreRead]:
    result = await session.exec(select(Store).where(Store.seller_id == seller.id))
    return [_store_read(store) for store in result.all()]


@router.post("/", response_model=StoreRead)
async def create_store(
    payload: StoreCreate,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> StoreRead:
    assert seller.id is not None, "Seller ID cannot be None"
    store = Store(
        name=payload.name,
        seller_id=seller.id,
        **address_from_payload(payload.address),
    )
    session.add(store)
    await session.commit()
    await session.refresh(store)
    return _store_read(store)


@router.get("/{store_id}", response_model=StoreRead)
async def get_store(
    store_id: int, session: AsyncSession = Depends(get_db_session)
) -> StoreRead:
    store = await session.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return _store_read(store)


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

@router.get("/{store_id}/inventory/all", response_model=List[StoreInventory])
async def list_store_inventory_all(
    store_id: int,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> List[StoreInventory]:
    """Return ALL inventory for a store (including unavailable) — seller only."""
    store = await session.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    if store.seller_id != seller.id and seller.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="Not authorized to view this store")

    result = await session.exec(
        select(StoreInventory).where(StoreInventory.store_id == store_id)
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

@router.put("/{store_id}/inventory/{inventory_id}", response_model=StoreInventory)
async def update_inventory(
    store_id: int,
    inventory_id: int,
    payload: StoreInventory,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> StoreInventory:
    """Update price, stock, or availability of an inventory item."""
    store = await session.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    if store.seller_id != seller.id and seller.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    inv = await session.get(StoreInventory, inventory_id)
    if not inv or inv.store_id != store_id:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    if payload.price is not None:
        inv.price = payload.price
    if payload.stock is not None:
        inv.stock = payload.stock
    if payload.is_available is not None:
        inv.is_available = payload.is_available

    session.add(inv)
    await session.commit()
    await session.refresh(inv)
    return inv

@router.delete("/{store_id}/inventory/{inventory_id}")
async def delete_inventory(
    store_id: int,
    inventory_id: int,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> dict[str, str]:
    """Remove a product from a store's inventory."""
    store = await session.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    if store.seller_id != seller.id and seller.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    inv = await session.get(StoreInventory, inventory_id)
    if not inv or inv.store_id != store_id:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    await session.delete(inv)
    await session.commit()
    return {"detail": "Inventory item deleted"}
