from typing import List

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User
from app.models.catalog import MasterProduct, MasterProductTranslation
from app.models.commerce import (
    Cart,
    CartItem,
    Delivery,
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.profile import CustomerAddress, CustomerProfile
from app.models.store import Store, StoreInventory
from app.schemas.address import address_to_payload
from app.services.inventory import decrement_stock, lock_inventory_rows
from app.utils.address import format_address


async def _customer_profile(session: AsyncSession, user: User) -> CustomerProfile:
    assert user.id is not None
    result = await session.exec(
        select(CustomerProfile).where(CustomerProfile.user_id == user.id)
    )
    profile = result.first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return profile


async def place_orders_from_cart(  # noqa: C901
    session: AsyncSession, user: User, customer_address_id: int
) -> List[Order]:
    profile = await _customer_profile(session, user)
    assert profile.id is not None

    addr_result = await session.exec(
        select(CustomerAddress, Address)
        .join(Address, Address.id == CustomerAddress.address_id)  # type: ignore[arg-type]
        .where(CustomerAddress.id == customer_address_id)
    )
    addr_row = addr_result.first()
    if addr_row is None:
        raise HTTPException(status_code=404, detail="invalid_address")
    customer_address, address = addr_row
    if customer_address.customer_profile_id != profile.id:
        raise HTTPException(status_code=403, detail="invalid_address")
    # Use the existing formatter so the snapshot matches the format the
    # rest of the app shows (Address has flat columns; format_address
    # accepts an AddressPayload via address_to_payload).
    address_snapshot = format_address(address_to_payload(address))

    cart_result = await session.exec(select(Cart).where(Cart.customer_profile_id == profile.id))
    carts = list(cart_result.all())
    if not carts:
        raise HTTPException(status_code=400, detail="cart_empty")

    cart_ids = [c.id for c in carts if c.id is not None]
    items_result = await session.exec(
        select(CartItem).where(CartItem.cart_id.in_(cart_ids))  # type: ignore[attr-defined]
    )
    cart_items = list(items_result.all())
    if not cart_items:
        raise HTTPException(status_code=400, detail="cart_empty")

    inv_ids = [item.inventory_id for item in cart_items]
    locked_inv = await lock_inventory_rows(session, inv_ids)
    inv_by_id = {inv.id: inv for inv in locked_inv}

    # Validate availability before any writes.
    qty_by_inv: dict[int, int] = {}
    for item in cart_items:
        qty_by_inv[item.inventory_id] = qty_by_inv.get(item.inventory_id, 0) + item.quantity
    for inv_id, requested in qty_by_inv.items():
        inv = inv_by_id.get(inv_id)
        if inv is None or not inv.is_available:
            raise HTTPException(status_code=409, detail={"detail": "item_unavailable", "inventory_ids": [inv_id]})
        if inv.stock < requested:
            raise HTTPException(status_code=409, detail={
                "detail": "insufficient_stock",
                "item": {"inventory_id": inv_id, "available_stock": inv.stock, "requested": requested},
            })

    # Validate stores active.
    store_ids = [c.store_id for c in carts]
    stores_result = await session.exec(select(Store).where(Store.id.in_(store_ids)))  # type: ignore[attr-defined]
    stores_by_id = {s.id: s for s in stores_result.all()}
    for c in carts:
        store = stores_by_id.get(c.store_id)
        if store is None or not store.is_active:
            raise HTTPException(status_code=409, detail={"detail": "store_unavailable", "store_id": c.store_id})

    # Snapshot product names: join via inventory → master_product → translation
    # filtered by 'en' (MVP — language plumbing comes later).
    name_rows = await session.exec(
        select(StoreInventory.id, MasterProduct.slug, MasterProductTranslation.name)
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .outerjoin(  # outerjoin so we still get a row even if translation missing
            MasterProductTranslation,
            (MasterProductTranslation.master_product_id == MasterProduct.id)
            & (MasterProductTranslation.language_code == "en"),
        )
        .where(StoreInventory.id.in_(inv_ids))  # type: ignore[attr-defined]
    )
    name_by_inv: dict[int, str] = {}
    for inv_id, slug, name in name_rows.all():
        name_by_inv[inv_id] = name or slug

    items_by_cart: dict[int, list[CartItem]] = {}
    for item in cart_items:
        items_by_cart.setdefault(item.cart_id, []).append(item)

    created_orders: list[Order] = []
    for cart in carts:
        assert cart.id is not None
        items = items_by_cart.get(cart.id, [])
        if not items:
            continue
        subtotal = sum(inv_by_id[i.inventory_id].price * i.quantity for i in items)
        delivery_fee = 0.0
        tax = 0.0
        total = subtotal + delivery_fee + tax

        order = Order(
            customer_profile_id=profile.id,
            store_id=cart.store_id,
            delivery_address_id=address.id,
            delivery_address_snapshot=address_snapshot,
            status=OrderStatus.Pending,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            tax=tax,
            total=total,
        )
        session.add(order)
        await session.flush()
        assert order.id is not None

        for item in items:
            inv = inv_by_id[item.inventory_id]
            session.add(OrderItem(
                order_id=order.id,
                inventory_id=item.inventory_id,
                product_name_snapshot=name_by_inv.get(item.inventory_id, "Item"),
                unit_price_snapshot=inv.price,
                quantity=item.quantity,
                line_total=inv.price * item.quantity,
            ))
            # Mutate the locked ORM instance — unit-of-work flushes the
            # change while the row lock is still held by this transaction.
            decrement_stock(inv, item.quantity)

        session.add(Payment(
            order_id=order.id,
            amount=total,
            method=PaymentMethod.Cash,
            status=PaymentStatus.Pending,
        ))
        session.add(Delivery(order_id=order.id, status=DeliveryStatus.Pending))
        created_orders.append(order)

    # Clear cart.
    for item in cart_items:
        await session.delete(item)
    for cart in carts:
        await session.delete(cart)

    await session.commit()
    for order in created_orders:
        await session.refresh(order)
    return created_orders
