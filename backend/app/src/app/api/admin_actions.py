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

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.base import User
from app.models.commerce import Order, OrderStatus
from app.schemas.admin_actions import RewindOrderRequest
from app.services.orders import rewind_order

router = APIRouter()


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
    return {"status": updated.status.value}
