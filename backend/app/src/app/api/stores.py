from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.locale import get_request_locale
from app.core.security import get_current_seller
from app.db.session import get_db_session
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import MasterProduct
from app.models.profile import SellerProfile
from app.models.store import Store, StoreInventory
from app.schemas.address import address_from_payload, address_to_payload
from app.schemas.inventory import (
    BulkInventoryError,
    BulkInventoryItem,
    BulkInventoryRequest,
)
from app.schemas.stores import StoreCreate, StoreRead
from app.services.inventory import (
    assert_products_in_seller_services,
    bulk_upsert_inventory,
)
from app.services.seller_services import list_profile_services

_BULK_ROW_LIMIT = 200

router = APIRouter()


async def _seller_profile_for_user(session: AsyncSession, user_id: int) -> SellerProfile:
    result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == user_id)
    )
    profile = result.first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    return profile


async def _store_read(session: AsyncSession, store: Store, lang: str = "en") -> StoreRead:
    assert store.id is not None
    services = await list_profile_services(
        session, store.seller_profile_id, language_code=lang
    )
    return StoreRead(
        id=store.id,
        name=store.name,
        address=address_to_payload(store.address),
        is_active=store.is_active,
        seller_id=store.seller_profile.user_id,
        services=services,
        created_at=store.created_at.isoformat(),
        updated_at=store.updated_at.isoformat(),
    )


def _store_with_relations_stmt() -> Any:
    return select(Store).options(
        selectinload(Store.address),  # type: ignore[arg-type]
        selectinload(Store.seller_profile),  # type: ignore[arg-type]
    )


async def _get_store_with_relations(
    session: AsyncSession, store_id: int
) -> Store | None:
    result = await session.exec(_store_with_relations_stmt().where(Store.id == store_id))
    store: Store | None = result.first()
    return store


@router.get("/", response_model=List[StoreRead])
async def list_stores(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(get_request_locale),
) -> List[StoreRead]:
    stmt = (
        _store_with_relations_stmt()
        .where(Store.is_active)
        .offset(skip)
        .limit(limit)
    )
    result = await session.exec(stmt)
    return [await _store_read(session, store, lang) for store in result.all()]


@router.get("/my", response_model=List[StoreRead])
async def list_my_stores(
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
    lang: str = Depends(get_request_locale),
) -> List[StoreRead]:
    assert seller.id is not None
    profile = await _seller_profile_for_user(session, seller.id)
    stmt = _store_with_relations_stmt().where(Store.seller_profile_id == profile.id)
    result = await session.exec(stmt)
    return [await _store_read(session, store, lang) for store in result.all()]


@router.post("/", response_model=StoreRead)
async def create_store(
    payload: StoreCreate,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> StoreRead:
    assert seller.id is not None, "Seller ID cannot be None"
    profile = await _seller_profile_for_user(session, seller.id)

    address = Address(**address_from_payload(payload.address))
    session.add(address)
    await session.flush()
    store = Store(
        name=payload.name,
        seller_profile_id=profile.id,
        address_id=address.id,
    )
    session.add(store)
    try:
        await session.flush()
        assert store.id is not None
        new_store_id = store.id
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Seller may have only one store"
        ) from exc

    # Reload with relations for the response
    refreshed = await _get_store_with_relations(session, new_store_id)
    assert refreshed is not None
    return await _store_read(session, refreshed)


@router.get("/{store_id}", response_model=StoreRead)
async def get_store(
    store_id: int,
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(get_request_locale),
) -> StoreRead:
    store = await _get_store_with_relations(session, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return await _store_read(session, store, lang)


# -------------------------------------------------------------
# Inventory API
# -------------------------------------------------------------


async def _authorize_store_ownership(
    session: AsyncSession, store_id: int, seller: User, allow_admin: bool = True
) -> Store:
    store = await _get_store_with_relations(session, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    is_admin = allow_admin and seller.role == UserRole.Admin
    if not is_admin and store.seller_profile.user_id != seller.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this store")
    return store


@router.get("/{store_id}/inventory", response_model=List[StoreInventory])
async def list_store_inventory(
    store_id: int, session: AsyncSession = Depends(get_db_session)
) -> List[StoreInventory]:
    store = await session.get(Store, store_id)
    if not store or not store.is_active:
        raise HTTPException(status_code=404, detail="Store not found or inactive")

    result = await session.exec(
        select(StoreInventory).where(
            StoreInventory.store_id == store_id, StoreInventory.is_available
        )
    )
    return list(result.all())


@router.get("/{store_id}/inventory/all", response_model=List[StoreInventory])
async def list_store_inventory_all(
    store_id: int,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> List[StoreInventory]:
    """Return ALL inventory for a store (including unavailable) — seller only."""
    await _authorize_store_ownership(session, store_id, seller)
    result = await session.exec(
        select(StoreInventory).where(StoreInventory.store_id == store_id)
    )
    return list(result.all())


@router.post("/{store_id}/inventory", response_model=StoreInventory)
async def add_inventory(
    store_id: int,
    inventory: StoreInventory,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> StoreInventory:
    store = await _authorize_store_ownership(
        session, store_id, seller, allow_admin=False
    )

    product = await session.get(MasterProduct, inventory.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Master product not found")

    await assert_products_in_seller_services(
        session, store.seller_profile_id, [inventory.product_id]
    )

    check_stmt = select(StoreInventory).where(
        StoreInventory.store_id == store_id,
        StoreInventory.product_id == inventory.product_id,
    )
    existing = await session.exec(check_stmt)
    if existing.first():
        raise HTTPException(
            status_code=400,
            detail="Product already exists in store inventory. Use PUT to update.",
        )

    inventory.id = None
    inventory.store_id = store_id
    session.add(inventory)
    await session.commit()
    await session.refresh(inventory)
    return inventory


def _validate_bulk_items(
    items: list[BulkInventoryItem],
) -> list[BulkInventoryError]:
    errs: list[BulkInventoryError] = []
    seen: set[int] = set()
    for idx, item in enumerate(items):
        if item.price <= 0 or item.price > 999_999:
            errs.append(
                BulkInventoryError(
                    index=idx,
                    product_id=item.product_id,
                    code="PRICE_INVALID",
                    message="Price must be > 0 and <= 999999",
                )
            )
        if item.stock < 0:
            errs.append(
                BulkInventoryError(
                    index=idx,
                    product_id=item.product_id,
                    code="STOCK_INVALID",
                    message="Stock must be >= 0",
                )
            )
        if item.product_id in seen:
            errs.append(
                BulkInventoryError(
                    index=idx,
                    product_id=item.product_id,
                    code="DUPLICATE_PRODUCT",
                    message="Product appears more than once",
                )
            )
        seen.add(item.product_id)
    return errs


@router.put("/{store_id}/inventory/bulk", response_model=List[StoreInventory])
async def bulk_upsert_store_inventory(
    store_id: int,
    payload: BulkInventoryRequest,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> List[StoreInventory]:
    store = await _authorize_store_ownership(
        session, store_id, seller, allow_admin=False
    )

    if len(payload.items) > _BULK_ROW_LIMIT:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ROW_LIMIT",
                "message": f"At most {_BULK_ROW_LIMIT} items per request",
            },
        )

    field_errors = _validate_bulk_items(payload.items)
    if field_errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": [e.model_dump() for e in field_errors]},
        )

    profile_id = store.seller_profile_id
    product_ids = [it.product_id for it in payload.items]
    await assert_products_in_seller_services(session, profile_id, product_ids)

    rows = await bulk_upsert_inventory(session, store_id, payload.items)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return rows


@router.put("/{store_id}/inventory/{inventory_id}", response_model=StoreInventory)
async def update_inventory(
    store_id: int,
    inventory_id: int,
    payload: StoreInventory,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> StoreInventory:
    """Update price, stock, or availability of an inventory item."""
    await _authorize_store_ownership(session, store_id, seller)

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
    await _authorize_store_ownership(session, store_id, seller)

    inv = await session.get(StoreInventory, inventory_id)
    if not inv or inv.store_id != store_id:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    await session.delete(inv)
    await session.commit()
    return {"detail": "Inventory item deleted"}
