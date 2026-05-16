# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.locale import get_request_locale
from app.core.security import get_current_seller, get_current_user
from app.db.session import get_db_session
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    CategoryTranslation,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.profile import SellerProfile, SellerProfileService
from app.models.store import Store, StoreInventory
from app.schemas.address import address_from_payload, address_to_payload
from app.schemas.inventory import (
    BulkInventoryError,
    BulkInventoryItem,
    BulkInventoryRequest,
)
from app.schemas.store_product_detail import (
    BreadcrumbPayload,
    InventoryWithProductPayload,
    MasterProductPayload,
    ServiceLite,
    StoreProductDetailResponse,
    StoreSummary,
)
from app.schemas.storefront import StorefrontResponse
from app.schemas.stores import StoreCreate, StoreRead, StoreUpdate
from app.services import inventory as services_inventory
from app.services.inventory import (
    assert_products_in_seller_services,
    bulk_upsert_inventory,
)
from app.services.seller_services import list_profile_services
from app.services.storefront import _translation_map, build_storefront

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


async def _store_read(
    session: AsyncSession,
    store: Store,
    lang: str = "en",
    *,
    distance_km: Optional[float] = None,
) -> StoreRead:
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
        delivery_radius_km=store.delivery_radius_km,
        pin_confirmed=store.pin_confirmed,
        distance_km=distance_km,
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
    lat: Optional[float] = Query(default=None, ge=-90.0, le=90.0),
    lng: Optional[float] = Query(default=None, ge=-180.0, le=180.0),
    radius_km: Optional[float] = Query(default=None, gt=0, le=100),
    sort: Optional[str] = Query(default=None, pattern="^distance$"),
    service: Optional[str] = Query(default=None, max_length=64),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(get_request_locale),
) -> List[StoreRead]:
    service_id: Optional[int] = None
    if service is not None:
        svc_row = await session.exec(
            select(Service.id).where(
                Service.slug == service,
                Service.is_active == True,  # noqa: E712
            )
        )
        service_id = svc_row.first()
        if service_id is None:
            raise HTTPException(status_code=400, detail="unknown_service")

    if lat is None or lng is None:
        stmt = (
            _store_with_relations_stmt()
            .where(Store.is_active)
        )
        if service_id is not None:
            stmt = stmt.where(
                Store.seller_profile_id.in_(  # type: ignore[attr-defined]
                    select(SellerProfileService.seller_profile_id).where(
                        SellerProfileService.service_id == service_id
                    )
                )
            )
        stmt = stmt.offset(skip).limit(limit)
        result = await session.exec(stmt)
        return [
            await _store_read(session, store, lang, distance_km=None)
            for store in result.all()
        ]

    point = "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography"
    if radius_km is not None:
        radius_clause = (
            f"ST_DWithin(a.geo, {point}, "
            "LEAST(s.delivery_radius_km, :user_cap) * 1000)"
        )
    else:
        radius_clause = (
            f"ST_DWithin(a.geo, {point}, s.delivery_radius_km * 1000)"
        )
    order_clause = (
        f"ST_Distance(a.geo, {point}) ASC" if sort == "distance" else "s.id ASC"
    )
    service_clause = (
        " AND EXISTS (SELECT 1 FROM sellerprofile_service sps "
        "WHERE sps.seller_profile_id = s.seller_profile_id "
        "AND sps.service_id = :service_id)"
        if service_id is not None
        else ""
    )
    sql = text(
        f"SELECT s.id, ST_Distance(a.geo, {point}) / 1000.0 AS distance_km "
        "FROM store s JOIN address a ON a.id = s.address_id "
        f"WHERE s.is_active AND a.geo IS NOT NULL AND {radius_clause}"
        f"{service_clause} "
        f"ORDER BY {order_clause} "
        "OFFSET :skip LIMIT :limit"
    )
    bind_params: dict[str, Any] = {
        "lat": lat, "lng": lng, "skip": skip, "limit": limit,
    }
    if radius_km is not None:
        bind_params["user_cap"] = radius_km
    if service_id is not None:
        bind_params["service_id"] = service_id
    rows = (
        await session.exec(sql.bindparams(**bind_params))  # type: ignore[call-overload]
    ).all()
    distance_by_id: dict[int, float] = {int(r[0]): float(r[1]) for r in rows}
    if not distance_by_id:
        return []
    stmt = (
        _store_with_relations_stmt().where(
            Store.id.in_(list(distance_by_id.keys()))  # type: ignore[union-attr]
        )
    )
    stores_unsorted = (await session.exec(stmt)).all()
    by_id = {s.id: s for s in stores_unsorted}
    ordered = [by_id[i] for i in distance_by_id.keys() if i in by_id]
    return [
        await _store_read(
            session, store, lang, distance_km=distance_by_id[store.id]
        )
        for store in ordered
    ]


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
        delivery_radius_km=payload.delivery_radius_km,
        pin_confirmed=payload.pin_confirmed,
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


@router.patch("/{store_id}", response_model=StoreRead)
async def update_store(
    store_id: int,
    payload: StoreUpdate,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
    lang: str = Depends(get_request_locale),
) -> StoreRead:
    store = await _authorize_store_ownership(session, store_id, seller, allow_admin=False)
    if payload.name is not None:
        store.name = payload.name
    if payload.delivery_radius_km is not None:
        store.delivery_radius_km = payload.delivery_radius_km
    if payload.pin_confirmed is not None:
        store.pin_confirmed = payload.pin_confirmed
    session.add(store)
    await session.commit()
    refreshed = await _get_store_with_relations(session, store_id)
    assert refreshed is not None
    return await _store_read(session, refreshed, lang)


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
        select(StoreInventory)
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
        .join(Category, Category.id == Subcategory.category_id)  # type: ignore[arg-type]
        .join(Service, Service.id == Category.service_id)  # type: ignore[arg-type]
        .where(
            StoreInventory.store_id == store_id,
            StoreInventory.is_available,
            MasterProduct.is_active == True,  # noqa: E712
            Subcategory.is_active == True,  # noqa: E712
            Category.is_active == True,  # noqa: E712
            Service.is_active == True,  # noqa: E712
        )
    )
    return list(result.all())


@router.get("/{store_id}/storefront", response_model=StorefrontResponse)
async def get_store_storefront(
    store_id: int,
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(get_request_locale),
) -> StorefrontResponse:
    """Aggregated storefront payload: store metadata + its available
    inventory grouped by service → category → subcategory, with localized
    names. Replaces the 6-fetch fan-out the store-detail page used to do
    (store + inventory + full master catalog + services + categories +
    subcategories) with a single request.
    """
    store = await _get_store_with_relations(session, store_id)
    if store is None or not store.is_active:
        raise HTTPException(status_code=404, detail="Store not found or inactive")
    store_read = await _store_read(session, store, lang)
    assert store.id is not None
    return await build_storefront(session, store_read, store.id, lang)


@router.get(
    "/{store_id}/products/{product_id}",
    response_model=StoreProductDetailResponse,
)
async def get_store_product_detail(
    store_id: int,
    product_id: int,
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(get_request_locale),
) -> StoreProductDetailResponse:
    """Per-store product detail. Powers the intercepted modal and the
    shareable full page. 404 when the store is unknown/inactive, or when
    the product is not stocked at this store. `is_available=false` and
    `stock=0` are still returned (frontend disables the CTA).
    """
    store = await session.get(Store, store_id)
    if store is None or not store.is_active:
        raise HTTPException(status_code=404, detail="Product not found at this store")

    join_stmt = (
        select(  # type: ignore[call-overload]
            StoreInventory, MasterProduct, Subcategory, Category, Service,
        )
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)
        .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)
        .join(Category, Category.id == Subcategory.category_id)
        .join(Service, Service.id == Category.service_id)
        .where(
            StoreInventory.store_id == store_id,
            StoreInventory.product_id == product_id,
            MasterProduct.is_active == True,  # noqa: E712
            Subcategory.is_active == True,  # noqa: E712
            Category.is_active == True,  # noqa: E712
            Service.is_active == True,  # noqa: E712
        )
    )
    row = (await session.exec(join_stmt)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found at this store")

    inv, product, sub, cat, svc = row
    assert inv.id is not None
    assert product.id is not None
    assert sub.id is not None
    assert cat.id is not None
    assert svc.id is not None
    assert store.id is not None

    product_t = await _translation_map(
        session, MasterProductTranslation, "master_product_id", [product.id], lang,
    )
    sub_t = await _translation_map(
        session, SubcategoryTranslation, "subcategory_id", [sub.id], lang,
    )
    cat_t = await _translation_map(
        session, CategoryTranslation, "category_id", [cat.id], lang,
    )
    svc_t = await _translation_map(
        session, ServiceTranslation, "service_id", [svc.id], lang,
    )

    product_translation = product_t.get(product.id)
    service_name = getattr(svc_t.get(svc.id), "name", None) or svc.slug
    category_name = getattr(cat_t.get(cat.id), "name", None) or cat.slug
    subcategory_name = getattr(sub_t.get(sub.id), "name", None) or sub.slug

    return StoreProductDetailResponse(
        store=StoreSummary(id=store.id, name=store.name),
        service=ServiceLite(id=svc.id, name=service_name),
        inventory=InventoryWithProductPayload(
            id=inv.id,
            store_id=inv.store_id,
            product_id=inv.product_id,
            price=float(inv.price),
            stock=inv.stock,
            is_available=inv.is_available,
            product=MasterProductPayload(
                id=product.id,
                name=getattr(product_translation, "name", None) or product.slug,
                description=getattr(product_translation, "description", None) or "",
                image_url=product.image_url,
                category_id=cat.id,
                subcategory_id=sub.id,
                subcategory_name=subcategory_name,
                base_price=float(product.base_price),
            ),
        ),
        breadcrumb=BreadcrumbPayload(
            service_id=svc.id,
            service_name=service_name,
            category_id=cat.id,
            category_name=category_name,
            subcategory_id=sub.id,
            subcategory_name=subcategory_name,
        ),
    )


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
    user: User = Depends(get_current_user),
) -> StoreInventory:
    """Add a product to a store's inventory.

    Sellers can only add to their own store. Admins can add on behalf of any
    approved seller; their write produces an ``inventory.create`` audit row.
    """
    store = await _authorize_store_ownership(
        session, store_id, user, allow_admin=True
    )
    acting_admin_id = user.id if user.role == UserRole.Admin else None
    return await services_inventory.create_inventory(
        session=session,
        store=store,
        inventory=inventory,
        acting_admin_id=acting_admin_id,
    )


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
    user: User = Depends(get_current_user),
) -> StoreInventory:
    """Update price, stock, or availability of an inventory item.

    Admins may update inventory on behalf of any approved seller. When an admin
    performs the write, an :class:`AdminActionLog` row is committed in the same
    transaction (see services.inventory.update_inventory).
    """
    store = await _authorize_store_ownership(session, store_id, user)

    inv = await session.get(StoreInventory, inventory_id)
    if not inv or inv.store_id != store_id:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    acting_admin_id = user.id if user.role == UserRole.Admin else None
    return await services_inventory.update_inventory(
        session=session,
        store=store,
        inv=inv,
        price=payload.price,
        stock=payload.stock,
        is_available=payload.is_available,
        acting_admin_id=acting_admin_id,
    )


@router.delete("/{store_id}/inventory/{inventory_id}")
async def delete_inventory(
    store_id: int,
    inventory_id: int,
    reason: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Remove a product from a store's inventory.

    Sellers delete their own items unconditionally. Admins may delete on
    behalf of any approved seller, but must supply ``?reason=`` (>=10 chars).
    Admin deletes are audit-logged.
    """
    store = await _authorize_store_ownership(session, store_id, user)

    inv = await session.get(StoreInventory, inventory_id)
    if not inv or inv.store_id != store_id:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    acting_admin_id = user.id if user.role == UserRole.Admin else None
    await services_inventory.delete_inventory(
        session=session,
        store=store,
        inv=inv,
        reason=reason,
        acting_admin_id=acting_admin_id,
    )
    return {"detail": "Inventory item deleted"}
