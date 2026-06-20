# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.locale import get_request_locale
from app.core.security import get_current_customer
from app.db.session import get_db_session
from app.models.address import Address
from app.models.base import User
from app.models.catalog import MasterProduct, MasterProductTranslation
from app.models.commerce import Cart, CartItem
from app.models.profile import CustomerAddress, CustomerProfile
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
from app.schemas.price_comparison import (
    CompareResponse,
    ReplaceAdjustment,
    ReplaceRequest,
    ReplaceResponse,
)
from app.services.price_comparison import find_alternatives

router = APIRouter()


DEFAULT_LANG = "en"


async def _product_names(
    session: AsyncSession, product_ids: list[int], lang: str = DEFAULT_LANG
) -> dict[int, str]:
    """Map product_id → display name in ``lang`` with English fallback."""
    if not product_ids:
        return {}
    result = await session.exec(
        select(MasterProductTranslation).where(
            MasterProductTranslation.master_product_id.in_(product_ids),  # type: ignore[attr-defined]
            MasterProductTranslation.language_code.in_({lang, DEFAULT_LANG}),  # type: ignore[attr-defined]
        )
    )
    by_lang: dict[int, dict[str, str]] = {}
    for row in result.all():
        by_lang.setdefault(row.master_product_id, {})[row.language_code] = row.name
    return {
        pid: name
        for pid, names in by_lang.items()
        if (name := names.get(lang) or names.get(DEFAULT_LANG)) is not None
    }


async def _service_names(
    session: AsyncSession, service_ids: list[int], lang: str = DEFAULT_LANG
) -> dict[int, str]:
    """Map service_id → display name in ``lang``, English then slug fallback."""
    if not service_ids:
        return {}
    from app.models.catalog import Service, ServiceTranslation

    slug_rows = await session.exec(
        select(Service.id, Service.slug).where(Service.id.in_(service_ids))  # type: ignore[union-attr]
    )
    slugs = {sid: slug for sid, slug in slug_rows.all() if sid is not None}

    tr_rows = await session.exec(
        select(
            ServiceTranslation.service_id,
            ServiceTranslation.language_code,
            ServiceTranslation.name,
        ).where(
            ServiceTranslation.service_id.in_(service_ids),  # type: ignore[attr-defined]
            ServiceTranslation.language_code.in_({lang, DEFAULT_LANG}),  # type: ignore[attr-defined]
        )
    )
    by_lang: dict[int, dict[str, str]] = {}
    for sid, code, name in tr_rows.all():
        by_lang.setdefault(sid, {})[code] = name

    return {
        sid: (by_lang.get(sid, {}).get(lang) or by_lang.get(sid, {}).get(DEFAULT_LANG) or slug)
        for sid, slug in slugs.items()
    }


async def _service_config(
    session: AsyncSession, carts: list[Cart]
) -> dict[tuple[int, int], tuple[float, float, int, int]]:
    """Map (store_id, service_id) -> (free_delivery_threshold, delivery_fee,
    eta_min, eta_max) for the carts' sellers."""
    if not carts:
        return {}
    from app.models.profile import SellerProfile, SellerProfileService

    store_ids = list({c.store_id for c in carts})
    rows = await session.exec(
        select(  # type: ignore[call-overload]
            Store.id,
            SellerProfileService.service_id,
            SellerProfileService.free_delivery_threshold,
            SellerProfileService.delivery_fee,
            SellerProfileService.delivery_eta_min_minutes,
            SellerProfileService.delivery_eta_max_minutes,
        )
        .join(SellerProfile, SellerProfile.id == Store.seller_profile_id)  # type: ignore[arg-type]
        .join(
            SellerProfileService,
            SellerProfileService.seller_profile_id == SellerProfile.id,  # type: ignore[arg-type]
        )
        .where(Store.id.in_(store_ids))  # type: ignore[union-attr]
    )
    return {
        (sid, svc): (thr, fee, emin, emax)
        for sid, svc, thr, fee, emin, emax in rows.all()
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


async def _serialize_carts(
    session: AsyncSession, carts: list[Cart], lang: str = DEFAULT_LANG
) -> list[CartRead]:
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

    name_by_product = await _product_names(session, list(product_ids), lang)
    name_by_service = await _service_names(session, [c.service_id for c in carts], lang)
    config_by_key = await _service_config(session, carts)

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
        cfg = config_by_key.get((cart.store_id, cart.service_id), (0.0, 0.0, 30, 60))
        out.append(
            CartRead(
                store_id=cart.store_id,
                store_name=store_name,
                service_id=cart.service_id,
                service_name=name_by_service.get(cart.service_id, str(cart.service_id)),
                items=items,
                subtotal=sum(i.line_total for i in items),
                free_delivery_threshold=cfg[0],
                delivery_fee=cfg[1],
                delivery_eta_min_minutes=cfg[2],
                delivery_eta_max_minutes=cfg[3],
            )
        )
    return out


@router.get("", response_model=CartListResponse)
@router.get("/", response_model=CartListResponse, include_in_schema=False)
async def list_carts(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
    lang: str = Depends(get_request_locale),
) -> CartListResponse:
    profile_id = await _customer_profile_id(session, user)
    result = await session.exec(
        select(Cart).where(Cart.customer_profile_id == profile_id)
    )
    carts = list(result.all())
    return CartListResponse(carts=await _serialize_carts(session, carts, lang))


async def _build_cart_item_response(
    session: AsyncSession, item: CartItem, lang: str = DEFAULT_LANG,
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
    names = await _product_names(session, [product.id], lang) if product.id else {}
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
    lang: str = Depends(get_request_locale),
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
    return await _build_cart_item_response(session, item, lang)


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
    lang: str = Depends(get_request_locale),
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
    return await _build_cart_item_response(session, item, lang)


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
    lang: str = Depends(get_request_locale),
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
        carts=await _serialize_carts(session, carts, lang),
        dropped=dropped,
    )


# ---------------------------------------------------------------------------
# Price comparison + cart-replace endpoints
# ---------------------------------------------------------------------------


async def _serialize_single_cart(
    session: AsyncSession, cart: Cart, lang: str = DEFAULT_LANG
) -> dict[str, object]:
    """Build a CartRead-shaped dict for a single cart, mirroring the loop
    in the existing list_carts handler."""
    store = await session.get(Store, cart.store_id)
    service_name = (await _service_names(session, [cart.service_id], lang)).get(
        cart.service_id, ""
    )
    config_by_key = await _service_config(session, [cart])
    items_result = await session.exec(
        select(CartItem, StoreInventory)
        .join(StoreInventory, StoreInventory.id == CartItem.inventory_id)  # type: ignore[arg-type]
        .where(CartItem.cart_id == cart.id)
    )
    rows = items_result.all()
    product_ids = [inv.product_id for _, inv in rows]
    names = await _product_names(session, product_ids, lang)
    items: list[dict[str, object]] = []
    subtotal = 0.0
    for ci, inv in rows:
        line_total = inv.price * ci.quantity
        subtotal += line_total
        items.append({
            "id": ci.id,
            "inventory_id": ci.inventory_id,
            "product_id": inv.product_id,
            "product_name": names.get(inv.product_id, ""),
            "unit_price": inv.price,
            "quantity": ci.quantity,
            "line_total": line_total,
        })
    cfg = config_by_key.get((cart.store_id, cart.service_id), (0.0, 0.0, 30, 60))
    return {
        "store_id": cart.store_id,
        "store_name": store.name if store else "",
        "service_id": cart.service_id,
        "service_name": service_name,
        "items": items,
        "subtotal": round(subtotal, 2),
        "free_delivery_threshold": cfg[0],
        "delivery_fee": cfg[1],
        "delivery_eta_min_minutes": cfg[2],
        "delivery_eta_max_minutes": cfg[3],
    }


@router.get(
    "/{store_id}/{service_id}/compare",
    response_model=CompareResponse,
)
async def compare_prices(
    store_id: int,
    service_id: int,
    customer_address_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
    lang: str = Depends(get_request_locale),
) -> CompareResponse:
    """Return ranked alternative stores for the customer's
    (store, service) cart."""
    profile_id = await _customer_profile_id(session, user)

    cart_result = await session.exec(
        select(Cart).where(
            Cart.customer_profile_id == profile_id,
            Cart.store_id == store_id,
            Cart.service_id == service_id,
        )
    )
    cart = cart_result.first()
    if cart is None:
        raise HTTPException(status_code=404, detail="cart_not_found")

    store_result = await session.exec(select(Store).where(Store.id == store_id))
    store = store_result.first()
    if store is None or not store.is_active:
        raise HTTPException(status_code=404, detail="store_not_found")

    await _validate_service_for_store(session, store_id, service_id)

    addr_result = await session.exec(
        select(CustomerAddress, Address)
        .join(Address, Address.id == CustomerAddress.address_id)  # type: ignore[arg-type]
        .where(CustomerAddress.id == customer_address_id)
    )
    addr_row = addr_result.first()
    if addr_row is None:
        raise HTTPException(status_code=400, detail="invalid_address")
    customer_address, address = addr_row
    if customer_address.customer_profile_id != profile_id:
        raise HTTPException(status_code=400, detail="invalid_address")
    if address.latitude is None or address.longitude is None:
        raise HTTPException(status_code=400, detail="invalid_address")

    items_result = await session.exec(
        select(CartItem, StoreInventory)
        .join(StoreInventory, StoreInventory.id == CartItem.inventory_id)  # type: ignore[arg-type]
        .where(CartItem.cart_id == cart.id)
    )
    cart_items: list[tuple[int, int]] = [
        (inv.product_id, ci.quantity) for ci, inv in items_result.all()
    ]
    if not cart_items:
        raise HTTPException(status_code=400, detail="cart_empty")

    alternatives = await find_alternatives(
        session,
        source_store_id=store_id,
        service_id=service_id,
        cart_items=cart_items,
        customer_latitude=address.latitude,
        customer_longitude=address.longitude,
        language_code=lang,
    )
    return CompareResponse(alternatives=alternatives)


@router.post(
    "/{store_id}/{service_id}/replace",
    response_model=ReplaceResponse,
)
async def replace_sub_basket(
    store_id: int,
    service_id: int,
    payload: ReplaceRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
    lang: str = Depends(get_request_locale),
) -> ReplaceResponse:
    """Atomically replace the customer's (store, service) sub-basket with
    the given items. Per-item failures (stock cap, unavailable) drop with
    adjustments. Whole-write failure returns 4xx."""
    profile_id = await _customer_profile_id(session, user)

    await _validate_service_for_store(session, store_id, service_id)

    granted_items: list[tuple[int, int]] = []
    adjustments: list[ReplaceAdjustment] = []

    for entry in payload.items:
        inv_result = await session.exec(
            select(StoreInventory).where(StoreInventory.id == entry.inventory_id)
        )
        inv = inv_result.first()
        if inv is None:
            raise HTTPException(status_code=404, detail="inventory_not_found")
        if inv.store_id != store_id:
            raise HTTPException(status_code=400, detail="inventory_store_mismatch")
        await _assert_inventory_service_match(session, entry.inventory_id, service_id)

        if not inv.is_available:
            adjustments.append(ReplaceAdjustment(
                inventory_id=entry.inventory_id,
                requested_quantity=entry.quantity,
                granted_quantity=0,
                reason="item_unavailable",
            ))
            continue
        if inv.stock <= 0:
            adjustments.append(ReplaceAdjustment(
                inventory_id=entry.inventory_id,
                requested_quantity=entry.quantity,
                granted_quantity=0,
                reason="stock_exhausted",
            ))
            continue
        granted_qty = min(entry.quantity, inv.stock)
        if granted_qty < entry.quantity:
            adjustments.append(ReplaceAdjustment(
                inventory_id=entry.inventory_id,
                requested_quantity=entry.quantity,
                granted_quantity=granted_qty,
                reason="stock_capped",
            ))
        granted_items.append((entry.inventory_id, granted_qty))

    if not granted_items:
        raise HTTPException(status_code=400, detail="empty_items")

    cart = await _get_or_create_cart(session, profile_id, store_id, service_id)
    assert cart.id is not None
    cart_id = cart.id
    existing = (await session.exec(
        select(CartItem).where(CartItem.cart_id == cart_id)
    )).all()
    for item in existing:
        await session.delete(item)
    await session.flush()
    for inventory_id, quantity in granted_items:
        session.add(CartItem(
            cart_id=cart_id, inventory_id=inventory_id, quantity=quantity,
        ))

    # Move semantics: when this replace is the target side of a checkout
    # "Shop at B" switch, remove the moved items from the source sub-basket
    # in the SAME transaction so the move is atomic (a failure above rolls
    # back both sides). Scoped by profile_id → cannot touch another user.
    if (
        payload.source_store_id is not None
        and payload.source_store_id != store_id
        and payload.source_inventory_ids
    ):
        source_cart = (await session.exec(
            select(Cart).where(
                Cart.customer_profile_id == profile_id,
                Cart.store_id == payload.source_store_id,
                Cart.service_id == service_id,
            )
        )).first()
        if source_cart is not None:
            # No source-side store/service validation (unlike the strict target
            # path above): we only ever delete rows that already live in the
            # caller's own source cart, so "delete-what's-there" cannot leak
            # across users or services — unmatched ids simply no-op.
            move_ids = set(payload.source_inventory_ids)
            source_items = (await session.exec(
                select(CartItem).where(CartItem.cart_id == source_cart.id)
            )).all()
            for item in source_items:
                if item.inventory_id in move_ids:
                    await session.delete(item)
            await session.flush()
            remaining = (await session.exec(
                select(CartItem).where(CartItem.cart_id == source_cart.id)
            )).first()
            if remaining is None:
                await session.delete(source_cart)

    await session.commit()

    refreshed = await session.get(Cart, cart_id)
    assert refreshed is not None
    cart_payload = await _serialize_single_cart(session, refreshed, lang)
    return ReplaceResponse(cart=cart_payload, adjustments=adjustments)
