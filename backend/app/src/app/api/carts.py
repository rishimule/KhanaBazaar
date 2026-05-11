# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_customer
from app.db.session import get_db_session
from app.models.base import User
from app.models.catalog import MasterProduct, MasterProductTranslation
from app.models.commerce import Cart, CartItem
from app.models.profile import CustomerProfile
from app.models.store import Store, StoreInventory
from app.schemas.carts import (
    CartItemAdd,
    CartItemRead,
    CartItemUpdate,
    CartListResponse,
    CartRead,
    CartSyncRequest,
    CartSyncResponse,
    DroppedSyncItem,
)

router = APIRouter()


# MVP: render product names in English. Future work can plumb the user's
# preferred_language from the User row through to this helper.
DEFAULT_LANG = "en"


async def _product_names(
    session: AsyncSession, product_ids: list[int]
) -> dict[int, str]:
    if not product_ids:
        return {}
    result = await session.exec(
        select(MasterProductTranslation).where(
            MasterProductTranslation.master_product_id.in_(product_ids),  # type: ignore[attr-defined]
            MasterProductTranslation.language_code == DEFAULT_LANG,
        )
    )
    return {row.master_product_id: row.name for row in result.all()}


async def _service_names(
    session: AsyncSession, service_ids: list[int]
) -> dict[int, str]:
    """Map service_id → display name. English translation, slug fallback."""
    if not service_ids:
        return {}
    from sqlalchemy import and_

    from app.models.catalog import Service, ServiceTranslation

    result = await session.exec(
        select(Service.id, Service.slug, ServiceTranslation.name)
        .outerjoin(
            ServiceTranslation,
            and_(
                ServiceTranslation.service_id == Service.id,  # type: ignore[arg-type]
                ServiceTranslation.language_code == DEFAULT_LANG,  # type: ignore[arg-type]
            ),
        )
        .where(Service.id.in_(service_ids))  # type: ignore[union-attr]
    )
    return {
        sid: (name or slug)
        for sid, slug, name in result.all()
        if sid is not None
    }


async def _customer_profile_id(session: AsyncSession, user: User) -> int:
    assert user.id is not None
    result = await session.exec(
        select(CustomerProfile.id).where(CustomerProfile.user_id == user.id)
    )
    profile_id = result.first()
    if profile_id is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return profile_id


async def _get_or_create_cart(
    session: AsyncSession,
    customer_profile_id: int,
    store_id: int,
    service_id: int,
) -> Cart:
    result = await session.exec(
        select(Cart).where(
            Cart.customer_profile_id == customer_profile_id,
            Cart.store_id == store_id,
            Cart.service_id == service_id,
        )
    )
    cart = result.first()
    if cart is None:
        # Validate store exists + active.
        store_result = await session.exec(select(Store).where(Store.id == store_id))
        store = store_result.first()
        if store is None or not store.is_active:
            raise HTTPException(status_code=404, detail="Store not found or inactive")
        cart = Cart(
            customer_profile_id=customer_profile_id,
            store_id=store_id,
            service_id=service_id,
        )
        session.add(cart)
        await session.flush()
    return cart


async def _validate_service_for_store(
    session: AsyncSession, store_id: int, service_id: int
) -> None:
    """Raise 409 service_unavailable if the store's seller does not offer
    `service_id`, or if Service.is_active is false."""
    from app.models.catalog import Service
    from app.models.profile import SellerProfile, SellerProfileService

    row = (
        await session.exec(
            select(SellerProfileService.id)
            .join(
                SellerProfile,
                SellerProfile.id == SellerProfileService.seller_profile_id,  # type: ignore[arg-type]
            )
            .join(Store, Store.seller_profile_id == SellerProfile.id)  # type: ignore[arg-type]
            .where(
                Store.id == store_id,
                SellerProfileService.service_id == service_id,
            )
        )
    ).first()
    service_active = (
        await session.exec(
            select(Service.is_active).where(Service.id == service_id)
        )
    ).first()
    if row is None or service_active is not True:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "service_unavailable",
                "store_id": store_id,
                "service_id": service_id,
            },
        )


async def _assert_inventory_service_match(
    session: AsyncSession, inventory_id: int, service_id: int
) -> None:
    """Raise 400 service_mismatch if `inventory_id`'s product resolves to a
    different `service_id` via subcategory→category."""
    from app.models.catalog import Category, Subcategory

    resolved = (
        await session.exec(
            select(Category.service_id)
            .join(Subcategory, Subcategory.category_id == Category.id)  # type: ignore[arg-type]
            .join(MasterProduct, MasterProduct.subcategory_id == Subcategory.id)  # type: ignore[arg-type]
            .join(StoreInventory, StoreInventory.product_id == MasterProduct.id)  # type: ignore[arg-type]
            .where(StoreInventory.id == inventory_id)
        )
    ).first()
    if resolved != service_id:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "service_mismatch",
                "inventory_id": inventory_id,
                "service_id": service_id,
            },
        )


async def _serialize_carts(session: AsyncSession, carts: list[Cart]) -> list[CartRead]:
    if not carts:
        return []
    cart_ids = [c.id for c in carts if c.id is not None]
    item_result = await session.exec(
        select(CartItem, StoreInventory, MasterProduct, Store)
        .join(StoreInventory, StoreInventory.id == CartItem.inventory_id)  # type: ignore[arg-type]
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .join(Store, Store.id == StoreInventory.store_id)  # type: ignore[arg-type]
        .where(CartItem.cart_id.in_(cart_ids))  # type: ignore[attr-defined]
    )
    rows = list(item_result.all())
    by_cart: dict[int, list[tuple[CartItem, StoreInventory, MasterProduct, Store]]] = {}
    product_ids: set[int] = set()
    for item, inv, product, store in rows:
        by_cart.setdefault(item.cart_id, []).append((item, inv, product, store))
        if product.id is not None:
            product_ids.add(product.id)

    name_by_product = await _product_names(session, list(product_ids))
    name_by_service = await _service_names(session, [c.service_id for c in carts])

    out: list[CartRead] = []
    for cart in carts:
        assert cart.id is not None
        rows_for_cart = by_cart.get(cart.id, [])
        items: list[CartItemRead] = []
        for item, inv, product, _ in rows_for_cart:
            assert item.id is not None
            assert inv.id is not None
            assert product.id is not None
            items.append(CartItemRead(
                id=item.id,
                inventory_id=inv.id,
                product_id=product.id,
                product_name=name_by_product.get(product.id, product.slug),
                unit_price=inv.price,
                quantity=item.quantity,
                line_total=inv.price * item.quantity,
            ))
        store_name = rows_for_cart[0][3].name if rows_for_cart else ""
        if not store_name:
            store_result = await session.exec(select(Store).where(Store.id == cart.store_id))
            store_row = store_result.first()
            store_name = store_row.name if store_row else ""
        out.append(
            CartRead(
                store_id=cart.store_id,
                store_name=store_name,
                service_id=cart.service_id,
                service_name=name_by_service.get(cart.service_id, str(cart.service_id)),
                items=items,
                subtotal=sum(i.line_total for i in items),
            )
        )
    return out


@router.get("", response_model=CartListResponse)
@router.get("/", response_model=CartListResponse, include_in_schema=False)
async def list_carts(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> CartListResponse:
    profile_id = await _customer_profile_id(session, user)
    result = await session.exec(
        select(Cart).where(Cart.customer_profile_id == profile_id)
    )
    carts = list(result.all())
    return CartListResponse(carts=await _serialize_carts(session, carts))


async def _build_cart_item_response(
    session: AsyncSession, item: CartItem,
) -> CartItemRead:
    """Build a CartItemRead from a persisted CartItem.

    Loads inventory + product + translation in one fresh query, so it is safe
    to call after a commit (does not rely on previously-loaded ORM instances
    whose attributes asyncpg has expired).
    """
    inv_result = await session.exec(
        select(StoreInventory, MasterProduct)
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .where(StoreInventory.id == item.inventory_id)
    )
    row = inv_result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="inventory_gone")
    inv, product = row
    names = await _product_names(session, [product.id]) if product.id else {}
    assert item.id is not None
    assert inv.id is not None
    assert product.id is not None
    return CartItemRead(
        id=item.id,
        inventory_id=inv.id,
        product_id=product.id,
        product_name=names.get(product.id, product.slug),
        unit_price=inv.price,
        quantity=item.quantity,
        line_total=inv.price * item.quantity,
    )


@router.post("/items", response_model=CartItemRead)
async def add_cart_item(
    payload: CartItemAdd,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> CartItemRead:
    profile_id = await _customer_profile_id(session, user)

    inv_result = await session.exec(
        select(StoreInventory).where(StoreInventory.id == payload.inventory_id)
    )
    inv = inv_result.first()
    if inv is None:
        raise HTTPException(status_code=404, detail="Inventory not found")
    if inv.store_id != payload.store_id:
        raise HTTPException(status_code=400, detail="inventory_store_mismatch")
    if not inv.is_available:
        raise HTTPException(status_code=409, detail="item_unavailable")

    await _validate_service_for_store(session, payload.store_id, payload.service_id)
    await _assert_inventory_service_match(
        session, payload.inventory_id, payload.service_id
    )

    cart = await _get_or_create_cart(
        session, profile_id, payload.store_id, payload.service_id
    )
    existing_result = await session.exec(
        select(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.inventory_id == payload.inventory_id,
        )
    )
    item = existing_result.first()
    updated = item is not None
    if item is None:
        item = CartItem(
            cart_id=cart.id, inventory_id=payload.inventory_id, quantity=payload.quantity
        )
        session.add(item)
    else:
        item.quantity += payload.quantity
    await session.commit()
    await session.refresh(item)

    response.status_code = status.HTTP_200_OK if updated else status.HTTP_201_CREATED
    return await _build_cart_item_response(session, item)


async def _owned_cart_item(
    session: AsyncSession, profile_id: int, item_id: int
) -> tuple[CartItem, Cart]:
    result = await session.exec(
        select(CartItem, Cart)
        .join(Cart, Cart.id == CartItem.cart_id)  # type: ignore[arg-type]
        .where(CartItem.id == item_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Cart item not found")
    item, cart = row
    if cart.customer_profile_id != profile_id:
        raise HTTPException(status_code=403, detail="not_your_item")
    return item, cart


@router.patch("/items/{item_id}", response_model=CartItemRead)
async def update_cart_item(
    item_id: int,
    payload: CartItemUpdate,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> CartItemRead:
    profile_id = await _customer_profile_id(session, user)
    item, _ = await _owned_cart_item(session, profile_id, item_id)

    # Re-validate availability so a customer cannot raise the quantity of an
    # item the seller just disabled. Mirrors the POST endpoint's contract.
    is_available = (await session.exec(
        select(StoreInventory.is_available).where(StoreInventory.id == item.inventory_id)
    )).first()
    if is_available is None:
        raise HTTPException(status_code=404, detail="inventory_gone")
    if not is_available:
        raise HTTPException(status_code=409, detail="item_unavailable")

    item.quantity = payload.quantity
    await session.commit()
    await session.refresh(item)
    return await _build_cart_item_response(session, item)


@router.delete("/items/{item_id}", status_code=204)
async def delete_cart_item(
    item_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> Response:
    profile_id = await _customer_profile_id(session, user)
    item, cart = await _owned_cart_item(session, profile_id, item_id)
    await session.delete(item)
    await session.flush()

    # Drop the cart if empty.
    remaining = await session.exec(select(CartItem).where(CartItem.cart_id == cart.id))
    if remaining.first() is None:
        await session.delete(cart)
    await session.commit()
    return Response(status_code=204)


@router.delete("/{store_id}/{service_id}", status_code=204)
async def clear_sub_basket_cart(
    store_id: int,
    service_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> Response:
    profile_id = await _customer_profile_id(session, user)
    cart_result = await session.exec(
        select(Cart).where(
            Cart.customer_profile_id == profile_id,
            Cart.store_id == store_id,
            Cart.service_id == service_id,
        )
    )
    cart = cart_result.first()
    if cart is not None:
        items_result = await session.exec(select(CartItem).where(CartItem.cart_id == cart.id))
        for item in items_result.all():
            await session.delete(item)
        await session.flush()
        await session.delete(cart)
        await session.commit()
    return Response(status_code=204)


@router.post("/sync", response_model=CartSyncResponse)
async def sync_carts(  # noqa: C901  # per-item validation branches; refactor tracked separately
    payload: CartSyncRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> CartSyncResponse:
    # TODO(perf): batch Store and StoreInventory lookups across the whole
    # payload before scaling sync beyond MVP-sized carts.
    profile_id = await _customer_profile_id(session, user)
    dropped: list[DroppedSyncItem] = []

    for cart_payload in payload.carts:
        store_result = await session.exec(
            select(Store).where(Store.id == cart_payload.store_id)
        )
        store = store_result.first()
        if store is None or not store.is_active:
            for it in cart_payload.items:
                dropped.append(DroppedSyncItem(
                    inventory_id=it.inventory_id, reason="store_unavailable",
                ))
            continue

        try:
            await _validate_service_for_store(
                session, cart_payload.store_id, cart_payload.service_id
            )
        except HTTPException:
            for it in cart_payload.items:
                dropped.append(DroppedSyncItem(
                    inventory_id=it.inventory_id, reason="service_unavailable",
                ))
            continue

        cart: Cart | None = None

        for item_payload in cart_payload.items:
            inv_result = await session.exec(
                select(StoreInventory).where(StoreInventory.id == item_payload.inventory_id)
            )
            inv = inv_result.first()
            if inv is None or inv.store_id != cart_payload.store_id or not inv.is_available:
                dropped.append(DroppedSyncItem(
                    inventory_id=item_payload.inventory_id,
                    reason="unknown_inventory" if inv is None else "item_unavailable",
                ))
                continue

            try:
                await _assert_inventory_service_match(
                    session, item_payload.inventory_id, cart_payload.service_id
                )
            except HTTPException:
                dropped.append(DroppedSyncItem(
                    inventory_id=item_payload.inventory_id, reason="service_mismatch",
                ))
                continue

            if cart is None:
                cart = await _get_or_create_cart(
                    session, profile_id, cart_payload.store_id, cart_payload.service_id
                )

            existing_result = await session.exec(
                select(CartItem).where(
                    CartItem.cart_id == cart.id,
                    CartItem.inventory_id == item_payload.inventory_id,
                )
            )
            existing = existing_result.first()
            if existing is None:
                session.add(CartItem(
                    cart_id=cart.id,
                    inventory_id=item_payload.inventory_id,
                    quantity=item_payload.quantity,
                ))
            else:
                existing.quantity += item_payload.quantity

    await session.commit()

    result = await session.exec(
        select(Cart).where(Cart.customer_profile_id == profile_id)
    )
    carts = list(result.all())
    return CartSyncResponse(
        carts=await _serialize_carts(session, carts),
        dropped=dropped,
    )
