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
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.admin_audit import AdminActionLog
from app.models.base import User
from app.models.catalog import (
    Category,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
)
from app.models.commerce import Delivery, Order, OrderStatus
from app.models.profile import SellerProfile, VerificationStatus
from app.models.seller_profile_change_request import (
    SellerProfileChangeRequest,
    SellerProfileChangeRequestEvent,
)
from app.models.store import Store, StoreInventory
from app.schemas.admin_actions import (
    ActivityLogPage,
    AdminActionLogOut,
    AdminInventoryRow,
    AdminMetricsRead,
    OrderServiceStat,
    OverrideDeliveryAddressRequest,
    RefundOrderRequest,
    RewindOrderRequest,
    SellerHubSummary,
)
from app.models.seller_onboarding_request import (
    OnboardingRequestStatus,
    SellerOnboardingRequest,
)
from app.schemas.pagination import PagedResponse
from app.schemas.seller_onboarding import (
    SellerOnboardingRequestRead,
    SellerOnboardingRequestStatusUpdate,
)
from app.schemas.seller_profile_change_request import (
    AdminQueueRow,
    ChangeRequestApproveBody,
    ChangeRequestEventRead,
    ChangeRequestNoteBody,
    ChangeRequestRead,
    ChangeRequestRejectBody,
)
from app.schemas.sellers import RevenueSeriesPoint, RevenueSeriesRead
from app.services.order_emails import dispatch_admin_order_action
from app.services.orders import (
    override_delivery_address,
    refund_order,
    rewind_order,
)
from app.services.seller_profile_change_requests import (
    OPEN_STATUSES,
)
from app.services.seller_profile_change_requests import (
    approve as approve_cr,
)
from app.services.seller_profile_change_requests import (
    reject as reject_cr,
)
from app.services.seller_profile_change_requests import (
    request_changes as request_changes_cr,
)
from app.services.seller_services import list_profile_services

router = APIRouter()


@router.get("/metrics", response_model=AdminMetricsRead)
async def admin_metrics(
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminMetricsRead:
    """Counts powering the admin dashboard. One round-trip; no caching."""
    ist = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(ist)
    today_start = now_ist.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    month_start = (
        now_ist.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        .astimezone(timezone.utc)
    )
    active = (OrderStatus.Pending, OrderStatus.Packed, OrderStatus.Dispatched)

    active_orders = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(Order)
        .where(Order.status.in_(active))  # type: ignore[attr-defined]
    )).one()
    orders_today = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(Order)
        .where(Order.placed_at >= today_start)
    )).one()
    orders_this_month = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(Order)
        .where(Order.placed_at >= month_start)
    )).one()
    # GMV counts orders DELIVERED this month (Delivery.delivered_at), not
    # orders placed this month.
    gmv_this_month = (await session.exec(
        select(func.coalesce(func.sum(Order.total), 0.0))  # type: ignore[arg-type]
        .select_from(Order)
        .join(Delivery, Delivery.order_id == Order.id)  # type: ignore[arg-type]
        .where(
            Order.status == OrderStatus.Delivered,
            Delivery.delivered_at >= month_start,
        )
    )).one()
    active_products = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(MasterProduct)
        .where(MasterProduct.is_active.is_(True))  # type: ignore[attr-defined]
    )).one()
    active_categories = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(Category)
        .where(Category.is_active.is_(True))  # type: ignore[attr-defined]
    )).one()
    active_stores = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(Store)
        .where(Store.is_active.is_(True))  # type: ignore[attr-defined]
    )).one()
    pending_apps = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(SellerProfile)
        .where(SellerProfile.verification_status == VerificationStatus.Pending)
    )).one()
    approved_sellers = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(SellerProfile)
        .where(SellerProfile.verification_status == VerificationStatus.Approved)
    )).one()
    open_crs = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(SellerProfileChangeRequest)
        .where(SellerProfileChangeRequest.status.in_(OPEN_STATUSES))  # type: ignore[attr-defined]
    )).one()

    # Previous calendar month window (IST), for the GMV trend.
    first_of_this_month_ist = now_ist.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    prev_month_start = (
        (first_of_this_month_ist - timedelta(days=1))
        .replace(day=1)
        .astimezone(timezone.utc)
    )
    prev_month_end = first_of_this_month_ist.astimezone(timezone.utc)
    gmv_last_month_raw = (await session.exec(
        select(func.coalesce(func.sum(Order.total), 0.0))  # type: ignore[arg-type]
        .select_from(Order)
        .join(Delivery, Delivery.order_id == Order.id)  # type: ignore[arg-type]
        .where(
            Order.status == OrderStatus.Delivered,
            Delivery.delivered_at >= prev_month_start,
            Delivery.delivered_at < prev_month_end,
        )
    )).one()
    rejected_sellers = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(SellerProfile)
        .where(SellerProfile.verification_status == VerificationStatus.Rejected)
    )).one()

    # Orders placed this month, grouped by service. Starts from every active
    # service and LEFT JOINs orders so services with zero orders still appear.
    obs_rows = (await session.exec(
        select(
            Service.id,
            ServiceTranslation.name,
            func.count(Order.id),  # type: ignore[arg-type]
        )
        .select_from(Service)
        .join(
            ServiceTranslation,
            and_(
                ServiceTranslation.service_id == Service.id,  # type: ignore[arg-type]
                ServiceTranslation.language_code == "en",  # type: ignore[arg-type]
            ),
            isouter=True,
        )
        .join(
            Order,
            and_(
                Order.service_id == Service.id,  # type: ignore[arg-type]
                Order.placed_at >= month_start,  # type: ignore[arg-type]
            ),
            isouter=True,
        )
        .where(Service.is_active.is_(True))  # type: ignore[attr-defined]
        .group_by(Service.id, ServiceTranslation.name)  # type: ignore[arg-type]
        .order_by(func.count(Order.id).desc(), Service.id)  # type: ignore[arg-type]
    )).all()
    orders_by_service = [
        OrderServiceStat(
            service_id=int(sid or 0),
            service_name=(name or f"Service {sid}"),
            count=int(cnt or 0),
        )
        for sid, name, cnt in obs_rows
    ]

    gmv_this_month_f = float(gmv_this_month or 0.0)
    gmv_last_month_f = float(gmv_last_month_raw or 0.0)
    gmv_trend_pct = (
        round((gmv_this_month_f - gmv_last_month_f) / gmv_last_month_f * 100, 1)
        if gmv_last_month_f
        else 0.0
    )

    return AdminMetricsRead(
        active_orders=int(active_orders),
        orders_today=int(orders_today),
        orders_this_month=int(orders_this_month),
        gmv_this_month=gmv_this_month_f,
        gmv_last_month=gmv_last_month_f,
        gmv_trend_pct=gmv_trend_pct,
        active_master_products=int(active_products),
        active_categories=int(active_categories),
        active_stores=int(active_stores),
        pending_applications=int(pending_apps),
        approved_sellers=int(approved_sellers),
        rejected_sellers=int(rejected_sellers),
        open_change_requests=int(open_crs),
        orders_by_service=orders_by_service,
    )


@router.get("/gmv-series", response_model=RevenueSeriesRead)
async def admin_gmv_series(
    range_token: Literal["7d", "14d", "30d"] = Query(default="14d", alias="range"),
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> RevenueSeriesRead:
    """Platform-wide daily gross-order-value series for the admin GMV chart.

    GOV = SUM(Order.total) for orders PLACED that IST day across all stores.
    Days with no orders are zero-filled so the line is continuous.
    """
    days = {"7d": 7, "14d": 14, "30d": 30}[range_token]

    ist = ZoneInfo("Asia/Kolkata")
    today = datetime.now(ist).date()
    start_date = today - timedelta(days=days - 1)
    start_utc = datetime.combine(start_date, time.min, tzinfo=ist).astimezone(timezone.utc)

    day_col = func.date(func.timezone("Asia/Kolkata", Order.placed_at))
    rows = (await session.exec(
        select(day_col, func.coalesce(func.sum(Order.total), 0.0))
        .select_from(Order)
        .where(Order.placed_at >= start_utc)
        .group_by(day_col)
    )).all()
    gov_by_date: dict[str, float] = {}
    for d, gov in rows:
        gov_by_date[d.isoformat() if hasattr(d, "isoformat") else str(d)] = float(gov or 0.0)

    points = [
        RevenueSeriesPoint(
            date=(start_date + timedelta(days=i)).isoformat(),
            gov=gov_by_date.get((start_date + timedelta(days=i)).isoformat(), 0.0),
        )
        for i in range(days)
    ]
    govs = [p.gov for p in points]
    avg_per_day = round(sum(govs) / days, 2) if days else 0.0
    peak = max(govs) if govs else 0.0
    return RevenueSeriesRead(points=points, avg_per_day=avg_per_day, peak=peak)


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
    assert profile.id is not None
    user = await session.get(User, profile.user_id)
    services = await list_profile_services(session, profile.id)

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
        store_paused=bool(store.is_paused) if store else False,
        active_order_count=active_count,
        total_product_count=product_count,
        services=services,
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


# -------------------------------------------------------------
# Admin: per-seller change-request management
# -------------------------------------------------------------


async def _admin_seller_profile_or_404(
    session: AsyncSession, seller_id: int
) -> SellerProfile:
    """Resolve a seller profile from the URL `seller_id` segment.

    `seller_id` in admin URLs is the seller's ``User.id`` (matches every other
    ``/admin/sellers/{seller_id}/*`` endpoint in this file). We resolve it via
    ``SellerProfile.user_id`` so callers can use ``profile.id`` for downstream
    queries.
    """
    from sqlalchemy.orm import selectinload

    profile = (
        await session.exec(
            select(SellerProfile)
            .where(SellerProfile.user_id == seller_id)
            .options(selectinload(SellerProfile.business_address))  # type: ignore[arg-type]
        )
    ).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="seller_not_found")
    return profile


async def _admin_load_cr(
    session: AsyncSession, profile_id: int, cr_id: uuid.UUID,
) -> SellerProfileChangeRequest:
    cr = (
        await session.exec(
            select(SellerProfileChangeRequest).where(
                SellerProfileChangeRequest.id == cr_id,
                SellerProfileChangeRequest.seller_profile_id == profile_id,
            )
        )
    ).first()
    if cr is None:
        raise HTTPException(status_code=404, detail="change_request_not_found")
    return cr


async def _admin_attach_events(
    session: AsyncSession, cr: SellerProfileChangeRequest
) -> ChangeRequestRead:
    events = (
        await session.exec(
            select(SellerProfileChangeRequestEvent)
            .where(SellerProfileChangeRequestEvent.change_request_id == cr.id)
            .order_by(SellerProfileChangeRequestEvent.created_at)  # type: ignore[arg-type]
        )
    ).all()
    payload = ChangeRequestRead.model_validate(cr)
    payload.events = [ChangeRequestEventRead.model_validate(e) for e in events]
    return payload


def _ensure_seller_active(profile: SellerProfile) -> None:
    if profile.verification_status is not VerificationStatus.Approved:
        raise HTTPException(status_code=409, detail="seller_not_active")


@router.get(
    "/sellers/{seller_id}/change-requests",
    response_model=list[ChangeRequestRead],
)
async def admin_list_seller_crs(
    seller_id: int,
    status: str = "open",
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[ChangeRequestRead]:
    profile = await _admin_seller_profile_or_404(session, seller_id)
    stmt = select(SellerProfileChangeRequest).where(
        SellerProfileChangeRequest.seller_profile_id == profile.id
    )
    if status == "open":
        stmt = stmt.where(
            SellerProfileChangeRequest.status.in_(OPEN_STATUSES)  # type: ignore[attr-defined]
        )
    elif status == "terminal":
        stmt = stmt.where(
            SellerProfileChangeRequest.status.notin_(OPEN_STATUSES)  # type: ignore[attr-defined]
        )
    stmt = stmt.order_by(
        SellerProfileChangeRequest.created_at.desc()  # type: ignore[attr-defined]
    )
    rows = (await session.exec(stmt)).all()
    return [ChangeRequestRead.model_validate(r) for r in rows]


@router.get(
    "/sellers/{seller_id}/change-requests/{cr_id}",
    response_model=ChangeRequestRead,
)
async def admin_get_seller_cr(
    seller_id: int,
    cr_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ChangeRequestRead:
    profile = await _admin_seller_profile_or_404(session, seller_id)
    assert profile.id is not None
    cr = await _admin_load_cr(session, profile.id, cr_id)
    return await _admin_attach_events(session, cr)


@router.post(
    "/sellers/{seller_id}/change-requests/{cr_id}/approve",
    response_model=ChangeRequestRead,
)
async def admin_approve_cr(
    seller_id: int,
    cr_id: uuid.UUID,
    body: ChangeRequestApproveBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ChangeRequestRead:
    profile = await _admin_seller_profile_or_404(session, seller_id)
    _ensure_seller_active(profile)
    assert profile.id is not None
    cr = await _admin_load_cr(session, profile.id, cr_id)
    res = await approve_cr(
        session=session,
        cr=cr,
        admin_user_id=admin.id,
        applied=body.applied,
        note=body.note,
    )
    # The in-service pre-check catches the common duplicate-phone case, but a
    # concurrent approval targeting the same number can still slip a unique
    # violation through to commit (TOCTOU). Convert it to a clean 409 instead
    # of leaking a 500.
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="phone_taken") from None
    await session.refresh(res.cr)
    for cb in res.emails:
        cb()
    return await _admin_attach_events(session, res.cr)


@router.post(
    "/sellers/{seller_id}/change-requests/{cr_id}/request-changes",
    response_model=ChangeRequestRead,
)
async def admin_request_changes_cr(
    seller_id: int,
    cr_id: uuid.UUID,
    body: ChangeRequestNoteBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ChangeRequestRead:
    profile = await _admin_seller_profile_or_404(session, seller_id)
    _ensure_seller_active(profile)
    assert profile.id is not None
    cr = await _admin_load_cr(session, profile.id, cr_id)
    res = await request_changes_cr(
        session=session, cr=cr, admin_user_id=admin.id, note=body.note,
    )
    await session.commit()
    await session.refresh(res.cr)
    for cb in res.emails:
        cb()
    return await _admin_attach_events(session, res.cr)


@router.post(
    "/sellers/{seller_id}/change-requests/{cr_id}/reject",
    response_model=ChangeRequestRead,
)
async def admin_reject_cr(
    seller_id: int,
    cr_id: uuid.UUID,
    body: ChangeRequestRejectBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ChangeRequestRead:
    profile = await _admin_seller_profile_or_404(session, seller_id)
    _ensure_seller_active(profile)
    assert profile.id is not None
    cr = await _admin_load_cr(session, profile.id, cr_id)
    res = await reject_cr(
        session=session, cr=cr, admin_user_id=admin.id, reason=body.reason,
    )
    await session.commit()
    await session.refresh(res.cr)
    for cb in res.emails:
        cb()
    return await _admin_attach_events(session, res.cr)


# ---------------------------------------------------------------------------
# Cross-seller change-request triage queue
# ---------------------------------------------------------------------------


@router.get("/change-requests", response_model=PagedResponse[AdminQueueRow])
async def admin_list_all_change_requests(
    status: str = "open",
    q: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> PagedResponse[AdminQueueRow]:
    """Cross-seller CR queue. Default returns open (submitted +
    changes_requested) ordered newest first. ``status=all|terminal`` opt-ins."""
    stmt = (
        select(SellerProfileChangeRequest, SellerProfile)
        .join(
            SellerProfile,
            SellerProfile.id == SellerProfileChangeRequest.seller_profile_id,  # type: ignore[arg-type]
        )
    )
    if status == "open":
        stmt = stmt.where(
            SellerProfileChangeRequest.status.in_(OPEN_STATUSES)  # type: ignore[attr-defined]
        )
    elif status == "terminal":
        stmt = stmt.where(
            SellerProfileChangeRequest.status.notin_(OPEN_STATUSES)  # type: ignore[attr-defined]
        )
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(SellerProfile.business_name.ilike(like))  # type: ignore[attr-defined]
    stmt = stmt.order_by(
        SellerProfileChangeRequest.updated_at.desc()  # type: ignore[attr-defined]
    )

    total = int((await session.exec(select(func.count()).select_from(stmt.subquery()))).one())

    rows = (await session.exec(stmt.offset((page - 1) * page_size).limit(page_size))).all()
    items = [
        AdminQueueRow(
            id=cr.id,
            seller_profile_id=cr.seller_profile_id,
            seller_user_id=profile.user_id,
            seller_business_name=profile.business_name,
            group=cr.group,
            status=cr.status,
            submission_count=cr.submission_count,
            created_at=cr.created_at,
            updated_at=cr.updated_at,
        )
        for cr, profile in rows
    ]


# --- Seller onboarding requests (visitor-submitted leads) -----------------


@router.get(
    "/onboarding-requests",
    response_model=PagedResponse[SellerOnboardingRequestRead],
)
async def admin_list_onboarding_requests(
    status: str = "all",
    q: Optional[str] = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> PagedResponse[SellerOnboardingRequestRead]:
    """List visitor-submitted seller-onboarding leads, newest first.

    ``status`` filters by lifecycle (``all`` = no filter); ``q`` matches store
    name / email / phone (case-insensitive).
    """
    stmt = select(SellerOnboardingRequest)
    if status != "all":
        try:
            stmt = stmt.where(
                SellerOnboardingRequest.status == OnboardingRequestStatus(status)
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail={"error": "invalid_status"}
            ) from exc
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                SellerOnboardingRequest.store_name.ilike(like),  # type: ignore[attr-defined]
                SellerOnboardingRequest.contact_email.ilike(like),  # type: ignore[attr-defined]
                SellerOnboardingRequest.contact_phone.ilike(like),  # type: ignore[attr-defined]
            )
        )
    total = (
        await session.exec(select(func.count()).select_from(stmt.subquery()))  # type: ignore[arg-type]
    ).one()
    rows = (
        await session.exec(
            stmt.order_by(SellerOnboardingRequest.created_at.desc())  # type: ignore[attr-defined]
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return PagedResponse(
        items=list(rows), total=total, page=page, page_size=page_size
    )


@router.patch(
    "/onboarding-requests/{request_id}",
    response_model=SellerOnboardingRequestRead,
)
async def admin_update_onboarding_request(
    request_id: int,
    body: SellerOnboardingRequestStatusUpdate,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> SellerOnboardingRequest:
    """Update the lifecycle status of an onboarding lead (admin triage)."""
    row = await session.get(SellerOnboardingRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    row.status = body.status
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row
    return PagedResponse(items=items, total=total, page=page, page_size=page_size)
