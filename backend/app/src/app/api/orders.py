# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import (  # noqa: F401
    get_current_admin,
    get_current_customer,
    get_current_seller,
    get_current_user,
)
from app.db.session import get_db_session
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    MasterProduct,
    MasterProductTranslation,
    Service,
    Subcategory,
)
from app.models.commerce import (
    Delivery,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    Review,
)
from app.models.profile import CustomerProfile, SellerProfile, SellerProfileService
from app.models.store import Store, StoreInventory
from app.schemas.orders import (
    DeliveryRead,
    OrderItemRead,
    OrderListResponse,
    OrderRead,
    OrderReviewInOrder,
    PaymentRead,
    PlaceOrderRequest,
    TransitionRequest,
)
from app.schemas.price_comparison import ReplaceAdjustment
from app.schemas.reorder import ReorderResolveResponse, ResolvedReorderItem
from app.schemas.reviews import OrderReviewCreate, OrderReviewRead
from app.services.checkout import place_order_for_sub_basket
from app.services.notification_push import dispatch_notification_push
from app.services.notifications import record_order_status_notification
from app.services.order_emails import (
    dispatch_admin_order_action,
    dispatch_order_placed,
    dispatch_order_status_changed,
)
from app.services.orders import cancel_order, transition_order_status

router = APIRouter()

logger = logging.getLogger(__name__)

REORDER_LANG = "en"

ACTIVE_STATUSES = (OrderStatus.Pending, OrderStatus.Packed, OrderStatus.Dispatched)
HISTORY_STATUSES = (OrderStatus.Delivered, OrderStatus.Cancelled)

_STATUS_COPY: dict[str, tuple[str, str]] = {
    "packed": ("Order #{oid} packed", "Your order has been packed and is being prepared."),
    "dispatched": ("Order #{oid} out for delivery", "Your order is on its way."),
    "delivered": ("Order #{oid} delivered", "Your order has been delivered. Enjoy!"),
    "cancelled": ("Order #{oid} cancelled", "Your order has been cancelled."),
}


async def record_and_dispatch_notification(
    session: AsyncSession, order: Order, status_value: str
) -> None:
    """Best-effort: persist an in-app notification and enqueue a web push.

    Order state is already committed by the caller; this opens a fresh write on
    the same session and never raises into the request path.
    """
    try:
        title_tpl, body = _STATUS_COPY.get(
            status_value, ("Order #{oid} updated", "Your order status changed.")
        )
        notif = await record_order_status_notification(
            session,
            customer_profile_id=order.customer_profile_id,
            order_id=order.id,
            status=status_value,
            title=title_tpl.format(oid=order.id),
            body=body,
        )
        if notif.id is not None:
            dispatch_notification_push(notif.id)
        # The commit above can expire `order` (the request session may use the
        # default expire_on_commit). Reload it so the caller can still serialize.
        await session.refresh(order)
    except Exception:
        logger.exception(
            "Failed to record/dispatch notification for order_id=%s", order.id
        )


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
    store_lat: Optional[float] = None
    store_lng: Optional[float] = None
    if store is not None:
        store_addr_result = await session.exec(
            select(Address).where(Address.id == store.address_id)
        )
        store_addr = store_addr_result.first()
        if store_addr is not None:
            store_lat = store_addr.latitude
            store_lng = store_addr.longitude
    delivery_addr_result = await session.exec(
        select(Address).where(Address.id == order.delivery_address_id)
    )
    delivery_addr = delivery_addr_result.first()
    delivery_lat = delivery_addr.latitude if delivery_addr else None
    delivery_lng = delivery_addr.longitude if delivery_addr else None
    review_result = await session.exec(select(Review).where(Review.order_id == order.id))
    review = review_result.first()
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
        service_id=order.service_id,
        service_name=order.service_name_snapshot,
        customer_name=customer_name,
        status=order.status,
        subtotal=order.subtotal,
        delivery_fee=order.delivery_fee,
        tax=order.tax,
        total=order.total,
        placed_at=order.placed_at,
        delivery_address_snapshot=order.delivery_address_snapshot,
        store_latitude=store_lat,
        store_longitude=store_lng,
        delivery_latitude=delivery_lat,
        delivery_longitude=delivery_lng,
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
        review=OrderReviewInOrder(rating=review.rating, comment=review.comment)
        if review is not None
        else None,
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
    service_id: Optional[int] = Query(default=None, gt=0),
    seller_id: Optional[int] = Query(default=None, gt=0),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderListResponse:
    """List orders.

    ``seller_id`` is an admin-only filter that scopes the listing to all
    stores belonging to one seller. Non-admin callers passing ``seller_id``
    receive 403.
    """
    statuses = _status_filter_for(status)
    stmt = select(Order)
    include_customer = False

    if seller_id is not None and user.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="forbidden")

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
        if service_id is not None:
            stmt = stmt.where(Order.service_id == service_id)
    elif user.role == UserRole.Seller:
        store_ids = await _seller_store_ids(session, user)
        if not store_ids:
            return OrderListResponse(orders=[])
        stmt = stmt.where(Order.store_id.in_(store_ids))  # type: ignore[attr-defined]
        include_customer = True
    elif user.role == UserRole.Admin:
        include_customer = True
        if seller_id is not None:
            # `seller_id` query param is the seller's User.id (matches the
            # /admin/sellers/{seller_id}/* convention shared with the seller
            # applications API). Resolve to SellerProfile.id, then to stores.
            profile_id = (await session.exec(
                select(SellerProfile.id).where(
                    SellerProfile.user_id == seller_id
                )
            )).first()
            if profile_id is None:
                return OrderListResponse(orders=[])
            seller_store_ids = [
                sid for sid in (await session.exec(
                    select(Store.id).where(Store.seller_profile_id == profile_id)
                )).all() if sid is not None
            ]
            if not seller_store_ids:
                return OrderListResponse(orders=[])
            stmt = stmt.where(Order.store_id.in_(seller_store_ids))  # type: ignore[attr-defined]
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
    order = await place_order_for_sub_basket(
        session,
        user,
        payload.customer_address_id,
        payload.store_id,
        payload.service_id,
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
        if user.role == UserRole.Admin:
            dispatch_admin_order_action(
                order.id, "order.transition", f"to {order.status.value}"
            )
        await record_and_dispatch_notification(session, order, order.status.value)
    return await _serialize_order(session, order, include_customer_name=include_customer)


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel(
    order_id: int,
    body: Optional[dict] = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrderRead:
    """Cancel an order.

    Customer: only on pending orders. Seller: any non-terminal order on a
    store they own. Admin: any non-terminal order — must supply
    ``{"reason": "..."}`` (>=10 chars) when the order is not pending.
    """
    reason = None
    if body and isinstance(body, dict):
        raw = body.get("reason")
        if isinstance(raw, str):
            reason = raw
    order, include_customer = await _load_order_for_user(session, order_id, user)
    order = await cancel_order(session, order, user, reason=reason)
    if order.id is not None:
        if user.role == UserRole.Admin:
            # Admin emails (admin_order_action_*) deliver the cancellation
            # notice to both audiences with reason + admin context, so the
            # generic status-changed email would just duplicate them.
            dispatch_admin_order_action(
                order.id, "order.cancel", reason or ""
            )
        else:
            dispatch_order_status_changed(
                order.id, "cancelled", notify_seller=True, reason=reason
            )
        # In-app notification fires for ALL roles (incl. admin), independent of
        # the role-based email branch above, so admin cancels are never silent.
        await record_and_dispatch_notification(session, order, "cancelled")
    return await _serialize_order(session, order, include_customer_name=include_customer)


@router.post("/{order_id}/review", response_model=OrderReviewRead)
async def create_order_review(
    order_id: int,
    body: OrderReviewCreate,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> OrderReviewRead:
    profile_id = await _customer_profile_id(session, user)
    order_result = await session.exec(select(Order).where(Order.id == order_id))
    order = order_result.first()
    if order is None or order.customer_profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != OrderStatus.Delivered:
        raise HTTPException(
            status_code=409, detail={"error": "order_not_delivered"}
        )
    existing_result = await session.exec(
        select(Review).where(Review.order_id == order.id)
    )
    if existing_result.first() is not None:
        raise HTTPException(status_code=409, detail={"error": "review_exists"})
    review = Review(
        customer_profile_id=profile_id,
        order_id=order.id,
        store_id=order.store_id,
        rating=body.rating,
        comment=body.comment,
    )
    session.add(review)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail={"error": "review_exists"}
        ) from exc
    await session.refresh(review)
    return OrderReviewRead(rating=review.rating, comment=review.comment)


async def _store_offers_service(
    session: AsyncSession, store_id: int, service_id: int
) -> bool:
    """True if the store's seller offers `service_id` and the service is active."""
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
    active = (
        await session.exec(select(Service.is_active).where(Service.id == service_id))
    ).first()
    return row is not None and active is True


@router.post("/{order_id}/reorder", response_model=ReorderResolveResponse)
async def reorder(
    order_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> ReorderResolveResponse:
    """Resolve a past order's items against current inventory (read-only).

    Returns cart-ready lines plus per-item adjustments for anything that is
    out of stock, capped, removed, or otherwise unavailable. Performs no
    writes — the frontend populates the cart from the response.
    """
    order, _ = await _load_order_for_user(session, order_id, user)

    store = await session.get(Store, order.store_id)
    store_name = store.name if store is not None else ""

    if not await _store_offers_service(session, order.store_id, order.service_id):
        raise HTTPException(status_code=409, detail="service_unavailable")

    order_items = (
        await session.exec(select(OrderItem).where(OrderItem.order_id == order_id))
    ).all()

    inv_ids = [i.inventory_id for i in order_items if i.inventory_id is not None]
    by_inv: dict[int, tuple[Any, ...]] = {}
    if inv_ids:
        rows = (
            await session.exec(
                select(  # type: ignore[call-overload]
                    StoreInventory.id,
                    StoreInventory.product_id,
                    StoreInventory.price,
                    StoreInventory.stock,
                    StoreInventory.is_available,
                    Category.service_id,
                    MasterProduct.image_url,
                    MasterProduct.slug,
                    MasterProductTranslation.name,
                )
                .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)
                .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)
                .join(Category, Category.id == Subcategory.category_id)
                .join(
                    MasterProductTranslation,
                    (MasterProductTranslation.master_product_id == MasterProduct.id)
                    & (MasterProductTranslation.language_code == REORDER_LANG),
                    isouter=True,
                )
                .where(
                    StoreInventory.id.in_(inv_ids),  # type: ignore[union-attr]
                    StoreInventory.store_id == order.store_id,
                )
            )
        ).all()
        by_inv = {r[0]: r for r in rows}

    items: list[ResolvedReorderItem] = []
    adjustments: list[ReplaceAdjustment] = []

    for it in order_items:
        inv_id = it.inventory_id
        row = by_inv.get(inv_id) if inv_id is not None else None
        if row is None:
            adjustments.append(ReplaceAdjustment(
                inventory_id=inv_id or 0, requested_quantity=it.quantity,
                granted_quantity=0, reason="item_unavailable",
            ))
            continue
        (_, product_id, price, stock, is_available, svc_id, image_url, slug, name) = row
        if svc_id != order.service_id or not is_available:
            adjustments.append(ReplaceAdjustment(
                inventory_id=inv_id, requested_quantity=it.quantity,
                granted_quantity=0, reason="item_unavailable",
            ))
            continue
        if stock <= 0:
            adjustments.append(ReplaceAdjustment(
                inventory_id=inv_id, requested_quantity=it.quantity,
                granted_quantity=0, reason="stock_exhausted",
            ))
            continue
        granted = min(it.quantity, stock)
        if granted < it.quantity:
            adjustments.append(ReplaceAdjustment(
                inventory_id=inv_id, requested_quantity=it.quantity,
                granted_quantity=granted, reason="stock_capped",
            ))
        items.append(ResolvedReorderItem(
            product_id=product_id, inventory_id=inv_id,
            product_name=name or slug, image_url=image_url,
            unit_price=price, quantity=granted,
        ))

    return ReorderResolveResponse(
        store_id=order.store_id, store_name=store_name,
        service_id=order.service_id, service_name=order.service_name_snapshot,
        items=items, adjustments=adjustments,
    )
