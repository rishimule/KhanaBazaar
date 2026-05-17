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

import base64
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.admin_audit import AdminActionLog
from app.models.base import User
from app.models.catalog import MasterProduct, MasterProductTranslation
from app.models.commerce import Order, OrderStatus
from app.models.profile import SellerProfile
from app.models.store import Store, StoreInventory
from app.schemas.admin_actions import (
    ActivityLogPage,
    AdminActionLogOut,
    AdminInventoryRow,
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


def _encode_cursor(created_at: datetime, row_id: str) -> str:
    payload = json.dumps({"t": created_at.isoformat(), "i": row_id})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(raw)
        return datetime.fromisoformat(data["t"]), data["i"]
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=400, detail={"code": "invalid_cursor"}
        ) from exc


async def _resolve_seller_profile_id(
    session: AsyncSession, user_id: int
) -> int:
    """``/admin/sellers/{id}/*`` accept the seller's ``User.id`` (matches the
    existing ``/sellers/admin/{seller_id}/verify`` convention used by the
    sellers list page). Resolve to ``SellerProfile.id`` for internal joins."""
    profile = (
        await session.exec(
            select(SellerProfile).where(SellerProfile.user_id == user_id)
        )
    ).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="seller_not_found")
    return profile.id


@router.get(
    "/sellers/{seller_id}/activity",
    response_model=ActivityLogPage,
)
async def admin_seller_activity(
    seller_id: int,
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ActivityLogPage:
    """Paginated admin audit log scoped to one seller.

    The ``{seller_id}`` path parameter is the seller's ``User.id`` (per the
    convention shared with ``/sellers/admin/{seller_id}/verify``). It is
    resolved to ``SellerProfile.id`` before the audit-log lookup.

    Ordered ``created_at DESC, id DESC``. Cursor is a base64-encoded
    ``(created_at_iso, id)`` tuple — id breaks ties on identical timestamps.
    """
    profile_id = await _resolve_seller_profile_id(session, seller_id)
    stmt = (
        select(AdminActionLog, User.email)
        .join(User, User.id == AdminActionLog.admin_user_id)  # type: ignore[arg-type]
        .where(AdminActionLog.target_seller_id == profile_id)
        .order_by(
            AdminActionLog.created_at.desc(),  # type: ignore[attr-defined]
            AdminActionLog.id.desc(),  # type: ignore[attr-defined]
        )
    )
    if cursor:
        ts, last_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                AdminActionLog.created_at < ts,
                and_(
                    AdminActionLog.created_at == ts,
                    AdminActionLog.id < last_id,  # type: ignore[arg-type]
                ),
            )
        )
    rows = list((await session.exec(stmt.limit(limit + 1))).all())

    next_cursor: Optional[str] = None
    if len(rows) > limit:
        rows = rows[:limit]
        last_row, _ = rows[-1]
        next_cursor = _encode_cursor(last_row.created_at, str(last_row.id))

    items = [
        AdminActionLogOut(
            id=str(row.id),
            admin_user_id=row.admin_user_id,
            admin_email=email,
            target_seller_id=row.target_seller_id,
            target_type=row.target_type.value,
            target_id=row.target_id,
            action=row.action,
            before_json=row.before_json,
            after_json=row.after_json,
            reason=row.reason,
            created_at=row.created_at.isoformat(),
        )
        for row, email in rows
    ]
    return ActivityLogPage(items=items, next_cursor=next_cursor)


@router.get("/sellers/{seller_id}", response_model=SellerHubSummary)
async def admin_seller_hub_summary(
    seller_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> SellerHubSummary:
    """Header data for the per-seller admin hub: profile + store + counts.

    ``seller_id`` is the seller's ``User.id`` (matches the existing
    ``/sellers/admin/{seller_id}/verify`` convention).
    """
    profile = (
        await session.exec(
            select(SellerProfile).where(SellerProfile.user_id == seller_id)
        )
    ).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="seller_not_found")
    user = await session.get(User, profile.user_id)

    store = (await session.exec(
        select(Store).where(Store.seller_profile_id == profile.id)
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


@router.get(
    "/sellers/{seller_id}/inventory",
    response_model=list[AdminInventoryRow],
)
async def admin_seller_inventory(
    seller_id: int,
    locale: str = Query(default="en", max_length=8),
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> list[AdminInventoryRow]:
    """Return all inventory for the seller's store enriched with the master
    product display name in the requested locale (falls back to ``en`` then
    the slug). Powers the admin Products tab.

    ``seller_id`` is the seller's ``User.id``.
    """
    profile = (
        await session.exec(
            select(SellerProfile).where(SellerProfile.user_id == seller_id)
        )
    ).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="seller_not_found")
    store = (
        await session.exec(
            select(Store).where(Store.seller_profile_id == profile.id)
        )
    ).first()
    if store is None:
        return []

    rows = list((await session.exec(
        select(StoreInventory).where(StoreInventory.store_id == store.id)
    )).all())
    if not rows:
        return []

    product_ids = [r.product_id for r in rows]
    products = list((await session.exec(
        select(MasterProduct).where(MasterProduct.id.in_(product_ids))  # type: ignore[union-attr]
    )).all())
    by_id = {p.id: p for p in products}

    # Look up names in requested locale, fall back to English, then slug.
    translations_for = await session.exec(
        select(MasterProductTranslation).where(
            MasterProductTranslation.master_product_id.in_(product_ids),  # type: ignore[union-attr]
            MasterProductTranslation.language_code.in_([locale, "en"]),  # type: ignore[union-attr]
        )
    )
    tx_by_product: dict[int, dict[str, str]] = {}
    for t in translations_for.all():
        tx_by_product.setdefault(t.master_product_id, {})[t.language_code] = t.name

    def name_for(product_id: int) -> str:
        tx = tx_by_product.get(product_id, {})
        return (
            tx.get(locale)
            or tx.get("en")
            or by_id.get(product_id, MasterProduct(slug="?", subcategory_id=0, base_price=0)).slug
        )

    return [
        AdminInventoryRow(
            id=r.id,
            store_id=r.store_id,
            product_id=r.product_id,
            product_name=name_for(r.product_id),
            product_brand=by_id.get(r.product_id).brand if by_id.get(r.product_id) else None,
            product_unit=by_id.get(r.product_id).unit if by_id.get(r.product_id) else None,
            price=r.price,
            stock=r.stock,
            is_available=r.is_available,
        )
        for r in rows
    ]


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
