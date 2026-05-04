from fastapi import HTTPException
from sqlalchemy import and_
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

# MVP pricing constants. When per-store fees and GST plug in, edit here so
# every Order row built from this service stays in sync.
MVP_DELIVERY_FEE = 0.0
MVP_TAX = 0.0


async def _customer_profile(session: AsyncSession, user: User) -> CustomerProfile:
    assert user.id is not None
    result = await session.exec(
        select(CustomerProfile).where(CustomerProfile.user_id == user.id)
    )
    profile = result.first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return profile


def _validate_inventory_availability(
    cart_items: list[CartItem], inv_by_id: dict[int, StoreInventory]
) -> None:
    """Sum cart-item quantities per inventory_id and raise 409 on the first
    unavailable / under-stocked row. Pure validation — no I/O, no mutation."""
    qty_by_inv: dict[int, int] = {}
    for item in cart_items:
        qty_by_inv[item.inventory_id] = qty_by_inv.get(item.inventory_id, 0) + item.quantity
    for inv_id, requested in qty_by_inv.items():
        inv = inv_by_id.get(inv_id)
        if inv is None or not inv.is_available:
            raise HTTPException(
                status_code=409,
                detail={"detail": "item_unavailable", "inventory_ids": [inv_id]},
            )
        if inv.stock < requested:
            raise HTTPException(status_code=409, detail={
                "detail": "insufficient_stock",
                "item": {"inventory_id": inv_id, "available_stock": inv.stock, "requested": requested},
            })


async def _validate_stores_active(
    session: AsyncSession, store_ids: list[int]
) -> None:
    """Raise 409 store_unavailable for the first inactive/missing store.
    Note: not row-locked — admin can race a deactivation here, which correctly
    produces a 409 and rolls back the inventory locks held by the caller."""
    stores_result = await session.exec(select(Store).where(Store.id.in_(store_ids)))  # type: ignore[union-attr]
    stores_by_id = {s.id: s for s in stores_result.all()}
    for store_id in store_ids:
        store = stores_by_id.get(store_id)
        if store is None or not store.is_active:
            raise HTTPException(status_code=409, detail={"detail": "store_unavailable", "store_id": store_id})


def _build_order_for_cart(
    *, profile_id: int, address_id: int, address_snapshot: str,
    cart: Cart, items: list[CartItem],
    inv_by_id: dict[int, StoreInventory], name_by_inv: dict[int, str],
    payment_method: PaymentMethod,
) -> tuple[Order, list[OrderItem], Payment, Delivery]:
    """Pure builder. Returns the rows to add and computes the line decrements
    via inv_by_id. Caller does session.add + decrement_stock."""
    subtotal = sum(inv_by_id[i.inventory_id].price * i.quantity for i in items)
    total = subtotal + MVP_DELIVERY_FEE + MVP_TAX
    order = Order(
        customer_profile_id=profile_id,
        store_id=cart.store_id,
        delivery_address_id=address_id,
        delivery_address_snapshot=address_snapshot,
        status=OrderStatus.Pending,
        subtotal=subtotal,
        delivery_fee=MVP_DELIVERY_FEE,
        tax=MVP_TAX,
        total=total,
    )
    order_items: list[OrderItem] = []
    for item in items:
        inv = inv_by_id[item.inventory_id]
        assert item.inventory_id in name_by_inv, (
            f"missing product name snapshot for inventory_id={item.inventory_id}"
        )
        order_items.append(OrderItem(
            inventory_id=item.inventory_id,
            product_name_snapshot=name_by_inv[item.inventory_id],
            unit_price_snapshot=inv.price,
            quantity=item.quantity,
            line_total=inv.price * item.quantity,
        ))
    payment = Payment(
        amount=total, method=payment_method, status=PaymentStatus.Pending,
    )
    delivery = Delivery(status=DeliveryStatus.Pending)
    return order, order_items, payment, delivery


async def _resolve_address(
    session: AsyncSession, customer_address_id: int, customer_profile_id: int
) -> tuple[int, str]:
    """Return (address_id, snapshot_string). 404 if missing; 403 if not owned
    by the calling customer. Both errors carry detail='invalid_address' so
    callers cannot distinguish missing from not-yours."""
    addr_result = await session.exec(
        select(CustomerAddress, Address)
        .join(Address, Address.id == CustomerAddress.address_id)  # type: ignore[arg-type]
        .where(CustomerAddress.id == customer_address_id)
    )
    addr_row = addr_result.first()
    if addr_row is None:
        raise HTTPException(status_code=404, detail="invalid_address")
    customer_address, address = addr_row
    if customer_address.customer_profile_id != customer_profile_id:
        raise HTTPException(status_code=403, detail="invalid_address")
    assert address.id is not None
    return address.id, format_address(address_to_payload(address))


async def _load_cart_for_store(
    session: AsyncSession, customer_profile_id: int, store_id: int
) -> tuple[Cart, list[CartItem]]:
    """Return (cart, items) for the customer's cart at this store. Raises
    404 cart_not_found if the customer has no cart row for store_id; 400
    cart_empty if the cart exists but has zero items."""
    cart_result = await session.exec(
        select(Cart).where(
            Cart.customer_profile_id == customer_profile_id,
            Cart.store_id == store_id,
        )
    )
    cart = cart_result.first()
    if cart is None:
        raise HTTPException(status_code=404, detail="cart_not_found")
    assert cart.id is not None
    items_result = await session.exec(
        select(CartItem).where(CartItem.cart_id == cart.id)
    )
    cart_items = list(items_result.all())
    if not cart_items:
        raise HTTPException(status_code=400, detail="cart_empty")
    return cart, cart_items


async def _snapshot_product_names(
    session: AsyncSession, inv_ids: list[int]
) -> dict[int, str]:
    """Build inventory_id → display name map. Joins MasterProductTranslation
    (English MVP) and falls back to MasterProduct.slug when the translation row
    is missing."""
    result = await session.exec(
        select(StoreInventory.id, MasterProduct.slug, MasterProductTranslation.name)
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .outerjoin(
            MasterProductTranslation,
            and_(
                MasterProductTranslation.master_product_id == MasterProduct.id,  # type: ignore[arg-type]
                MasterProductTranslation.language_code == "en",  # type: ignore[arg-type]
            ),
        )
        .where(StoreInventory.id.in_(inv_ids))  # type: ignore[union-attr]
    )
    return {
        inv_id: (name or slug)
        for inv_id, slug, name in result.all()
        if inv_id is not None
    }


async def place_order_for_store(
    session: AsyncSession,
    user: User,
    customer_address_id: int,
    store_id: int,
    payment_method: PaymentMethod,
) -> Order:
    profile = await _customer_profile(session, user)
    assert profile.id is not None

    address_id, address_snapshot = await _resolve_address(
        session, customer_address_id, profile.id
    )

    cart, cart_items = await _load_cart_for_store(session, profile.id, store_id)

    inv_ids = [item.inventory_id for item in cart_items]
    locked_inv = await lock_inventory_rows(session, inv_ids)
    inv_by_id: dict[int, StoreInventory] = {
        inv.id: inv for inv in locked_inv if inv.id is not None
    }

    _validate_inventory_availability(cart_items, inv_by_id)
    await _validate_stores_active(session, [store_id])

    name_by_inv = await _snapshot_product_names(session, inv_ids)

    order, order_items, payment, delivery = _build_order_for_cart(
        profile_id=profile.id, address_id=address_id,
        address_snapshot=address_snapshot, cart=cart, items=cart_items,
        inv_by_id=inv_by_id, name_by_inv=name_by_inv,
        payment_method=payment_method,
    )
    session.add(order)
    await session.flush()
    assert order.id is not None
    for oi in order_items:
        oi.order_id = order.id
        session.add(oi)
        # Mutate the locked ORM instance — unit-of-work flushes the change
        # while the row lock is still held by this transaction.
        assert oi.inventory_id is not None
        decrement_stock(inv_by_id[oi.inventory_id], oi.quantity)
    payment.order_id = order.id
    delivery.order_id = order.id
    session.add(payment)
    session.add(delivery)

    # Clear only this store's cart (items first to satisfy the FK).
    for item in cart_items:
        await session.delete(item)
    await session.flush()
    await session.delete(cart)

    await session.commit()
    await session.refresh(order)
    return order
