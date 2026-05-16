# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin-supervisor router mounted at ``/api/v1/admin``.

Exposes admin-only operations on a single seller's store + orders:
- ``GET    /admin/sellers/{seller_id}`` — hub summary
- ``GET    /admin/sellers/{seller_id}/activity`` — paginated audit log
- ``POST   /admin/orders/{order_id}/rewind`` — backward status transition
- ``POST   /admin/orders/{order_id}/refund`` — mark payment refunded
- ``PATCH  /admin/orders/{order_id}/delivery-address`` — override snapshot

All routes are guarded by :func:`get_current_admin`. Every write emits an
:class:`AdminActionLog` row in the same DB transaction as the mutation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlalchemy import func

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.base import User
from app.models.commerce import Order, OrderStatus
from app.models.profile import SellerProfile
from app.models.store import Store, StoreInventory
from app.schemas.admin_actions import (
    OverrideDeliveryAddressRequest,
    RefundOrderRequest,
    RewindOrderRequest,
    SellerHubSummary,
)
from app.services.order_emails import dispatch_admin_order_action
from app.services.orders import (
    override_delivery_address,
    refund_order,
    rewind_order,
)

router = APIRouter()


@router.get("/sellers/{seller_id}", response_model=SellerHubSummary)
async def admin_seller_hub_summary(
    seller_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> SellerHubSummary:
    """Header data for the per-seller admin hub: profile + store + counts."""
    profile = await session.get(SellerProfile, seller_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="seller_not_found")
    user = await session.get(User, profile.user_id)

    store = (await session.exec(
        select(Store).where(Store.seller_profile_id == seller_id)
    )).first()

    active_count = 0
    product_count = 0
    if store is not None:
        active_count = int((await session.exec(
            select(func.count(Order.id)).where(
                Order.store_id == store.id,
                Order.status.in_(  # type: ignore[attr-defined]
                    [
                        OrderStatus.Pending,
                        OrderStatus.Packed,
                        OrderStatus.Dispatched,
                    ]
                ),
            )
        )).first() or 0)
        product_count = int((await session.exec(
            select(func.count(StoreInventory.id)).where(
                StoreInventory.store_id == store.id
            )
        )).first() or 0)

    return SellerHubSummary(
        seller_id=seller_id,
        business_name=profile.business_name,
        verification_status=profile.verification_status.value,
        email=user.email if user else "",
        store_id=store.id if store else None,
        active_order_count=active_count,
        total_product_count=product_count,
    )


@router.post("/orders/{order_id}/rewind")
async def admin_rewind_order(
    order_id: int,
    payload: RewindOrderRequest,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    order = (
        await session.exec(select(Order).where(Order.id == order_id))
    ).first()
    if order is None:
        raise HTTPException(status_code=404, detail="order_not_found")
    target = OrderStatus(payload.to_status)
    updated = await rewind_order(
        session=session,
        order=order,
        to_status=target,
        reason=payload.reason,
        acting_admin_id=admin.id,
    )
    if updated.id is not None:
        dispatch_admin_order_action(updated.id, "order.rewind", payload.reason)
    return {"status": updated.status.value}


@router.post("/orders/{order_id}/refund")
async def admin_refund_order(
    order_id: int,
    payload: RefundOrderRequest,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    order = (
        await session.exec(select(Order).where(Order.id == order_id))
    ).first()
    if order is None:
        raise HTTPException(status_code=404, detail="order_not_found")
    await refund_order(
        session=session,
        order=order,
        reason=payload.reason,
        acting_admin_id=admin.id,
    )
    if order.id is not None:
        dispatch_admin_order_action(order.id, "order.refund", payload.reason)
    return {"status": "refunded"}


@router.patch("/orders/{order_id}/delivery-address")
async def admin_override_delivery_address(
    order_id: int,
    payload: OverrideDeliveryAddressRequest,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    order = (
        await session.exec(select(Order).where(Order.id == order_id))
    ).first()
    if order is None:
        raise HTTPException(status_code=404, detail="order_not_found")
    await override_delivery_address(
        session=session,
        order=order,
        address_payload=payload.address,
        reason=payload.reason,
        acting_admin_id=admin.id,
    )
    if order.id is not None:
        dispatch_admin_order_action(
            order.id, "order.address_override", payload.reason
        )
    return {"status": "updated"}
