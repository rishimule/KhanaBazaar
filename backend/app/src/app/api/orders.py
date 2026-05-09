# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import (  # noqa: F401
    get_current_admin,
    get_current_customer,
    get_current_seller,
    get_current_user,
)
from app.db.session import get_db_session
from app.models.base import User, UserRole
from app.models.commerce import (
    Delivery,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
)
from app.models.profile import CustomerProfile, SellerProfile
from app.models.store import Store
from app.schemas.orders import (
    DeliveryRead,
    OrderItemRead,
    OrderListResponse,
    OrderRead,
    PaymentRead,
    PlaceOrderRequest,
    TransitionRequest,
)
from app.services.checkout import place_order_for_store
from app.services.order_emails import (
    dispatch_order_placed,
    dispatch_order_status_changed,
)
from app.services.orders import cancel_order, transition_order_status

router = APIRouter()

ACTIVE_STATUSES = (OrderStatus.Pending, OrderStatus.Packed, OrderStatus.Dispatched)
HISTORY_STATUSES = (OrderStatus.Delivered, OrderStatus.Cancelled)


async def _serialize_order(session: AsyncSession, order: Order, *, include_customer_name: bool) -> OrderRead:
    # TODO(perf): when list_orders calls this in a loop the round-trips compound
    # (4-5 SELECTs per order × 50). Batch-load items/payments/deliveries/stores
    # via WHERE order_id IN (...) before scaling list payloads.
    assert order.id is not None
    items_result = await session.exec(select(OrderItem).where(OrderItem.order_id == order.id))
    items = list(items_result.all())
    for it in items:
        assert it.id is not None
    payment_result = await session.exec(select(Payment).where(Payment.order_id == order.id))
    payment = payment_result.first()
    if payment is None:
        raise HTTPException(status_code=500, detail="order_missing_payment")
    delivery_result = await session.exec(select(Delivery).where(Delivery.order_id == order.id))
    delivery = delivery_result.first()
    if delivery is None:
        raise HTTPException(status_code=500, detail="order_missing_delivery")
    store_result = await session.exec(select(Store).where(Store.id == order.store_id))
    store = store_result.first()
    customer_name: Optional[str] = None
    if include_customer_name:
        cust_result = await session.exec(
            select(CustomerProfile).where(CustomerProfile.id == order.customer_profile_id)
        )
        cust = cust_result.first()
        if cust is not None:
            parts = [p for p in (cust.first_name, cust.last_name) if p]
            customer_name = " ".join(parts) if parts else None
    return OrderRead(
        id=order.id,
        store_id=order.store_id,
        store_name=store.name if store else "",
        customer_name=customer_name,
        status=order.status,
        subtotal=order.subtotal,
        delivery_fee=order.delivery_fee,
        tax=order.tax,
        total=order.total,
        placed_at=order.placed_at,
        delivery_address_snapshot=order.delivery_address_snapshot,
        items=[OrderItemRead(
            id=i.id,
            inventory_id=i.inventory_id,
            product_name_snapshot=i.product_name_snapshot,
            unit_price_snapshot=i.unit_price_snapshot,
            quantity=i.quantity,
            line_total=i.line_total,
        ) for i in items],
        payment=PaymentRead(
            method=payment.method, status=payment.status, amount=payment.amount, paid_at=payment.paid_at,
        ),
        delivery=DeliveryRead(
            status=delivery.status,
            packed_at=delivery.packed_at,
            dispatched_at=delivery.dispatched_at,
            delivered_at=delivery.delivered_at,
        ),
    )


def _status_filter_for(status_param: Optional[str]) -> Optional[tuple[OrderStatus, ...]]:
    if status_param is None:
        return None
    if status_param == "active":
        return ACTIVE_STATUSES
    if status_param == "history":
        return HISTORY_STATUSES
    raise HTTPException(status_code=400, detail="invalid_status_filter")


async def _seller_store_ids(session: AsyncSession, user: User) -> list[int]:
    profile_result = await session.exec(
        select(SellerProfile.id).where(SellerProfile.user_id == user.id)
    )
    profile_id = profile_result.first()
    if profile_id is None:
        return []
    store_result = await session.exec(
        select(Store.id).where(Store.seller_profile_id == profile_id)
    )
    return [sid for sid in store_result.all() if sid is not None]


async def _customer_profile_id(session: AsyncSession, user: User) -> int:
    result = await session.exec(
        select(CustomerProfile.id).where(CustomerProfile.user_id == user.id)
    )
    profile_id = result.first()
    if profile_id is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return profile_id


@router.get("", response_model=OrderListResponse)
@router.get("/", response_model=OrderListResponse, include_in_schema=False)
async def list_orders(
    status: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderListResponse:
    statuses = _status_filter_for(status)
    stmt = select(Order)
    include_customer = False

    if user.role == UserRole.Customer:
        # A logged-in customer with no CustomerProfile (incomplete onboarding)
        # naturally has no orders; return [] instead of leaking via 404.
        profile_result = await session.exec(
            select(CustomerProfile.id).where(CustomerProfile.user_id == user.id)
        )
        profile_id = profile_result.first()
        if profile_id is None:
            return OrderListResponse(orders=[])
        stmt = stmt.where(Order.customer_profile_id == profile_id)
    elif user.role == UserRole.Seller:
        store_ids = await _seller_store_ids(session, user)
        if not store_ids:
            return OrderListResponse(orders=[])
        stmt = stmt.where(Order.store_id.in_(store_ids))  # type: ignore[attr-defined]
        include_customer = True
    elif user.role == UserRole.Admin:
        include_customer = True
    else:
        raise HTTPException(status_code=403, detail="forbidden")

    if statuses is not None:
        stmt = stmt.where(Order.status.in_(statuses))  # type: ignore[attr-defined]

    stmt = stmt.order_by(Order.placed_at.desc()).limit(50)  # type: ignore[attr-defined]
    result = await session.exec(stmt)
    orders = list(result.all())
    return OrderListResponse(
        orders=[await _serialize_order(session, o, include_customer_name=include_customer) for o in orders],
    )


async def _load_order_for_user(session: AsyncSession, order_id: int, user: User) -> tuple[Order, bool]:
    """Load an order, enforce role-based access, return (order, include_customer_name)."""
    result = await session.exec(select(Order).where(Order.id == order_id))
    order = result.first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if user.role == UserRole.Customer:
        profile_id = await _customer_profile_id(session, user)
        if order.customer_profile_id != profile_id:
            raise HTTPException(status_code=403, detail="forbidden")
        return order, False
    if user.role == UserRole.Seller:
        store_ids = await _seller_store_ids(session, user)
        if order.store_id not in store_ids:
            raise HTTPException(status_code=403, detail="forbidden")
        return order, True
    if user.role == UserRole.Admin:
        return order, True
    raise HTTPException(status_code=403, detail="forbidden")


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderRead:
    order, include_customer = await _load_order_for_user(session, order_id, user)
    return await _serialize_order(session, order, include_customer_name=include_customer)


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=OrderRead, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def place_order(
    payload: PlaceOrderRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> OrderRead:
    order = await place_order_for_store(
        session,
        user,
        payload.customer_address_id,
        payload.store_id,
        payload.payment_method,
    )
    if order.id is not None:
        dispatch_order_placed([order.id])
    return await _serialize_order(session, order, include_customer_name=False)


@router.post("/{order_id}/transition", response_model=OrderRead)
async def transition_order(
    order_id: int,
    payload: TransitionRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderRead:
    if user.role not in (UserRole.Seller, UserRole.Admin):
        raise HTTPException(status_code=403, detail="forbidden")
    order, include_customer = await _load_order_for_user(session, order_id, user)
    order = await transition_order_status(session, order, payload.to, user)
    if order.id is not None:
        dispatch_order_status_changed(order.id, order.status.value)
    return await _serialize_order(session, order, include_customer_name=include_customer)


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel(
    order_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderRead:
    order, include_customer = await _load_order_for_user(session, order_id, user)
    order = await cancel_order(session, order, user)
    if order.id is not None:
        dispatch_order_status_changed(order.id, "cancelled", notify_seller=True)
    return await _serialize_order(session, order, include_customer_name=include_customer)
