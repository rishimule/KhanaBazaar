from typing import List  # noqa: F401

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import selectinload  # noqa: F401
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_customer
from app.db.session import get_db_session
from app.models.base import User
from app.models.catalog import MasterProduct, MasterProductTranslation
from app.models.commerce import Cart, CartItem
from app.models.profile import CustomerProfile
from app.models.store import Store, StoreInventory

# These schemas are re-exported here so the endpoints landing in follow-up
# tasks (Tasks 4-7) can import them from this module without churn.
from app.schemas.carts import (  # noqa: F401
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
    session: AsyncSession, customer_profile_id: int, store_id: int
) -> Cart:
    result = await session.exec(
        select(Cart).where(
            Cart.customer_profile_id == customer_profile_id,
            Cart.store_id == store_id,
        )
    )
    cart = result.first()
    if cart is None:
        # Validate store exists + active.
        store_result = await session.exec(select(Store).where(Store.id == store_id))
        store = store_result.first()
        if store is None or not store.is_active:
            raise HTTPException(status_code=404, detail="Store not found or inactive")
        cart = Cart(customer_profile_id=customer_profile_id, store_id=store_id)
        session.add(cart)
        await session.flush()
    return cart


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

    out: list[CartRead] = []
    for cart in carts:
        assert cart.id is not None
        rows_for_cart = by_cart.get(cart.id, [])
        items = [
            CartItemRead(
                id=item.id,  # type: ignore[arg-type]
                inventory_id=inv.id,  # type: ignore[arg-type]
                product_id=product.id,  # type: ignore[arg-type]
                product_name=name_by_product.get(product.id, product.slug),
                unit_price=inv.price,
                quantity=item.quantity,
                line_total=inv.price * item.quantity,
            )
            for item, inv, product, _ in rows_for_cart
        ]
        store_name = rows_for_cart[0][3].name if rows_for_cart else ""
        if not store_name:
            store_result = await session.exec(select(Store).where(Store.id == cart.store_id))
            store = store_result.first()
            store_name = store.name if store else ""
        out.append(
            CartRead(
                store_id=cart.store_id,
                store_name=store_name,
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


@router.post("/items", response_model=CartItemRead)
async def add_cart_item(
    payload: CartItemAdd,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> CartItemRead:
    profile_id = await _customer_profile_id(session, user)

    inv_result = await session.exec(
        select(StoreInventory, MasterProduct)
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .where(StoreInventory.id == payload.inventory_id)
    )
    row = inv_result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Inventory not found")
    inv, product = row
    if inv.store_id != payload.store_id:
        raise HTTPException(status_code=400, detail="inventory_store_mismatch")
    if not inv.is_available:
        raise HTTPException(status_code=409, detail="item_unavailable")

    # Capture scalar values before commit, since SQLAlchemy expires ORM
    # attributes on commit and lazy reload triggers sync IO under asyncpg.
    inv_id = inv.id
    inv_price = inv.price
    product_id = product.id
    product_slug = product.slug
    names = await _product_names(session, [product_id]) if product_id else {}
    product_name = names.get(product_id, product_slug)

    cart = await _get_or_create_cart(session, profile_id, payload.store_id)
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
    return CartItemRead(
        id=item.id,  # type: ignore[arg-type]
        inventory_id=inv_id,  # type: ignore[arg-type]
        product_id=product_id,  # type: ignore[arg-type]
        product_name=product_name,
        unit_price=inv_price,
        quantity=item.quantity,
        line_total=inv_price * item.quantity,
    )


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
    item.quantity = payload.quantity
    # Capture inventory + product info BEFORE commit (asyncpg expires ORM
    # attributes on commit and lazy reload triggers sync IO).
    inv_result = await session.exec(
        select(StoreInventory, MasterProduct)
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .where(StoreInventory.id == item.inventory_id)
    )
    inv, product = inv_result.first()  # type: ignore[misc]
    inv_id = inv.id
    inv_price = inv.price
    product_id = product.id
    product_slug = product.slug
    names = await _product_names(session, [product_id]) if product_id else {}
    product_name = names.get(product_id, product_slug)

    await session.commit()
    await session.refresh(item)

    return CartItemRead(
        id=item.id,  # type: ignore[arg-type]
        inventory_id=inv_id,  # type: ignore[arg-type]
        product_id=product_id,  # type: ignore[arg-type]
        product_name=product_name,
        unit_price=inv_price,
        quantity=item.quantity,
        line_total=inv_price * item.quantity,
    )


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


@router.delete("/{store_id}", status_code=204)
async def clear_store_cart(
    store_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> Response:
    profile_id = await _customer_profile_id(session, user)
    cart_result = await session.exec(
        select(Cart).where(
            Cart.customer_profile_id == profile_id, Cart.store_id == store_id
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
