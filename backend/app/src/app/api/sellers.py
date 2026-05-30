# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, time, timedelta, timezone
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, desc, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.locale import get_request_locale
from app.core.security import get_current_admin, get_current_seller
from app.db.session import get_db_session
from app.models.address import Address, LocationSource
from app.models.admin_audit import AdminActionTargetType
from app.models.base import User
from app.models.catalog import (
    Category,
    MasterProduct,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.commerce import Delivery, Order, OrderStatus
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from app.models.seller_profile_change_request import (
    SellerProfileChangeGroup,
)
from app.models.store import Store, StoreInventory
from app.schemas.address import address_from_payload, address_to_payload
from app.schemas.inventory import EligibleProduct
from app.schemas.pagination import PagedResponse
from app.schemas.sellers import (
    AdminSetServicesBody,
    InventoryServiceStat,
    OrderStatusCounts,
    RevenueSeriesPoint,
    RevenueSeriesRead,
    SellerApplicationPayload,
    SellerMetricsRead,
    SellerProfilePayload,
    SellerProfileUpdateBody,
    SetServiceMinOrderValueBody,
    TopSubcategory,
)
from app.schemas.services import ServicePayload
from app.schemas.stores import StorePauseBody, StoreRead
from app.services import admin_audit
from app.services.eligible_products import list_eligible_products
from app.services.profiles import compose_full_name, split_full_name
from app.services.seller_emails import (
    dispatch_seller_application_submitted,
    dispatch_seller_approved,
    dispatch_seller_rejected,
)
from app.services.seller_profile_change_requests import supersede_open_cr
from app.services.seller_services import (
    list_profile_services,
    replace_profile_services,
    validate_service_ids,
)
from app.services.store_pause import set_service_pause, set_store_pause

router = APIRouter()


async def _seller_profile_with_address(
    session: AsyncSession, user_id: int
) -> SellerProfile | None:
    stmt = (
        select(SellerProfile)
        .where(SellerProfile.user_id == user_id)
        .options(selectinload(SellerProfile.business_address))  # type: ignore[arg-type]
    )
    result = await session.exec(stmt)
    return result.first()


async def _seller_store(session: AsyncSession, user_id: int) -> Store:
    profile_res = await session.exec(
        select(SellerProfile.id).where(SellerProfile.user_id == user_id)
    )
    profile_id = profile_res.first()
    if profile_id is None:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    store = (
        await session.exec(
            select(Store)
            .where(Store.seller_profile_id == profile_id)
            .options(
                selectinload(Store.address),  # type: ignore[arg-type]
                selectinload(Store.seller_profile),  # type: ignore[arg-type]
            )
        )
    ).first()
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


@router.get("/me/metrics", response_model=SellerMetricsRead)
async def get_seller_metrics(
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> SellerMetricsRead:
    """Counts powering the seller dashboard. One round-trip; no caching."""
    profile_res = await session.exec(
        select(SellerProfile.id).where(SellerProfile.user_id == current_user.id)
    )
    profile_id = profile_res.first()
    if profile_id is None:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    store_res = await session.exec(
        select(Store).where(Store.seller_profile_id == profile_id)
    )
    store = store_res.first()
    if store is None:
        return SellerMetricsRead(
            active_orders=0,
            orders_today=0,
            orders_this_month=0,
            revenue_this_month=0.0,
            revenue_last_month=0.0,
            revenue_trend_pct=0.0,
            total_products=0,
            out_of_stock=0,
            unavailable=0,
            store_active=False,
            store_paused=False,
            pin_confirmed=False,
            store_name="",
            order_status_counts=OrderStatusCounts(),
            inventory_by_service=[],
            top_subcategory=None,
        )

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
        .where(Order.store_id == store.id, Order.status.in_(active))  # type: ignore[attr-defined]
    )).one()
    orders_today = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(Order)
        .where(Order.store_id == store.id, Order.placed_at >= today_start)
    )).one()
    orders_this_month = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(Order)
        .where(Order.store_id == store.id, Order.placed_at >= month_start)
    )).one()
    # Revenue counts orders DELIVERED this month (Delivery.delivered_at window),
    # not orders placed this month — matches accounting expectations even when
    # an order placed last month is fulfilled this month.
    revenue_this_month_raw = (await session.exec(
        select(func.coalesce(func.sum(Order.total), 0.0))  # type: ignore[arg-type]
        .select_from(Order)
        .join(Delivery, Delivery.order_id == Order.id)  # type: ignore[arg-type]
        .where(
            Order.store_id == store.id,
            Order.status == OrderStatus.Delivered,
            Delivery.delivered_at >= month_start,
        )
    )).one()
    # Previous calendar month window (IST), for the revenue trend.
    first_of_this_month_ist = now_ist.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    prev_month_start = (
        (first_of_this_month_ist - timedelta(days=1))
        .replace(day=1)
        .astimezone(timezone.utc)
    )
    prev_month_end = first_of_this_month_ist.astimezone(timezone.utc)
    revenue_last_month_raw = (await session.exec(
        select(func.coalesce(func.sum(Order.total), 0.0))  # type: ignore[arg-type]
        .select_from(Order)
        .join(Delivery, Delivery.order_id == Order.id)  # type: ignore[arg-type]
        .where(
            Order.store_id == store.id,
            Order.status == OrderStatus.Delivered,
            Delivery.delivered_at >= prev_month_start,
            Delivery.delivered_at < prev_month_end,
        )
    )).one()
    total_products = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(StoreInventory)
        .where(StoreInventory.store_id == store.id)
    )).one()
    out_of_stock = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(StoreInventory)
        .where(StoreInventory.store_id == store.id, StoreInventory.stock == 0)
    )).one()
    unavailable = (await session.exec(
        select(func.count())  # type: ignore[arg-type]
        .select_from(StoreInventory)
        .where(StoreInventory.store_id == store.id, StoreInventory.is_available.is_(False))  # type: ignore[attr-defined]
    )).one()

    # Lifetime status mix for the donut.
    status_rows = (await session.exec(
        select(Order.status, func.count())
        .select_from(Order)
        .where(Order.store_id == store.id)
        .group_by(Order.status)
    )).all()
    counts = OrderStatusCounts()
    for st, cnt in status_rows:
        key = st.value if hasattr(st, "value") else str(st)
        if hasattr(counts, key):
            setattr(counts, key, int(cnt))

    # Inventory grouped by service.
    in_stock_expr = func.coalesce(
        func.sum(
            case(
                (
                    and_(
                        StoreInventory.stock > 0,  # type: ignore[arg-type]
                        StoreInventory.is_available.is_(True),  # type: ignore[attr-defined]
                    ),
                    1,
                ),
                else_=0,
            )
        ),
        0,
    )
    svc_rows = (await session.exec(
        select(
            Service.id,
            ServiceTranslation.name,
            func.count(StoreInventory.id),  # type: ignore[arg-type]
            in_stock_expr,
        )
        .select_from(StoreInventory)
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
        .join(Category, Category.id == Subcategory.category_id)  # type: ignore[arg-type]
        .join(Service, Service.id == Category.service_id)  # type: ignore[arg-type]
        .join(
            ServiceTranslation,
            and_(
                ServiceTranslation.service_id == Service.id,  # type: ignore[arg-type]
                ServiceTranslation.language_code == "en",  # type: ignore[arg-type]
            ),
            isouter=True,
        )
        .where(StoreInventory.store_id == store.id)
        .group_by(Service.id, ServiceTranslation.name)  # type: ignore[arg-type]
    )).all()
    inventory_by_service = [
        InventoryServiceStat(
            service_id=int(sid or 0),
            service_name=(name or f"Service {sid}"),
            in_stock=int(in_stock or 0),
            total=int(total or 0),
        )
        for sid, name, total, in_stock in svc_rows
    ]

    # Most-stocked subcategory (in-stock rows) for the inventory footer.
    top_row = (await session.exec(
        select(
            SubcategoryTranslation.name,
            func.count(StoreInventory.id).label("c"),  # type: ignore[arg-type]
        )
        .select_from(StoreInventory)
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
        .join(
            SubcategoryTranslation,
            and_(
                SubcategoryTranslation.subcategory_id == Subcategory.id,  # type: ignore[arg-type]
                SubcategoryTranslation.language_code == "en",  # type: ignore[arg-type]
            ),
            isouter=True,
        )
        .where(
            StoreInventory.store_id == store.id,
            StoreInventory.stock > 0,
            StoreInventory.is_available.is_(True),  # type: ignore[attr-defined]
        )
        .group_by(Subcategory.id, SubcategoryTranslation.name)  # type: ignore[arg-type]
        .order_by(desc("c"))
        .limit(1)
    )).first()
    top_subcategory = (
        TopSubcategory(name=(top_row[0] or "—"), count=int(top_row[1]))
        if top_row is not None
        else None
    )

    revenue_this_month = float(revenue_this_month_raw or 0.0)
    revenue_last_month = float(revenue_last_month_raw or 0.0)
    revenue_trend_pct = (
        round((revenue_this_month - revenue_last_month) / revenue_last_month * 100, 1)
        if revenue_last_month
        else 0.0
    )

    return SellerMetricsRead(
        active_orders=int(active_orders),
        orders_today=int(orders_today),
        orders_this_month=int(orders_this_month),
        revenue_this_month=revenue_this_month,
        revenue_last_month=revenue_last_month,
        revenue_trend_pct=revenue_trend_pct,
        total_products=int(total_products),
        out_of_stock=int(out_of_stock),
        unavailable=int(unavailable),
        store_active=bool(store.is_active),
        store_paused=bool(store.is_paused),
        pin_confirmed=bool(store.pin_confirmed),
        store_name=store.name,
        order_status_counts=counts,
        inventory_by_service=inventory_by_service,
        top_subcategory=top_subcategory,
    )


@router.get("/me/revenue-series", response_model=RevenueSeriesRead)
async def get_revenue_series(
    range_token: Literal["7d", "14d", "30d"] = Query(default="14d", alias="range"),
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> RevenueSeriesRead:
    """Daily gross-order-value series for the dashboard revenue chart.

    GOV = SUM(Order.total) for orders PLACED that IST day. Days with no orders
    are zero-filled so the line is continuous.
    """
    days = {"7d": 7, "14d": 14, "30d": 30}[range_token]

    profile_res = await session.exec(
        select(SellerProfile.id).where(SellerProfile.user_id == current_user.id)
    )
    profile_id = profile_res.first()
    if profile_id is None:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    store_res = await session.exec(
        select(Store).where(Store.seller_profile_id == profile_id)
    )
    store = store_res.first()

    ist = ZoneInfo("Asia/Kolkata")
    today = datetime.now(ist).date()
    start_date = today - timedelta(days=days - 1)

    gov_by_date: dict[str, float] = {}
    if store is not None:
        start_utc = datetime.combine(start_date, time.min, tzinfo=ist).astimezone(timezone.utc)
        day_col = func.date(func.timezone("Asia/Kolkata", Order.placed_at))
        rows = (await session.exec(
            select(day_col, func.coalesce(func.sum(Order.total), 0.0))
            .select_from(Order)
            .where(Order.store_id == store.id, Order.placed_at >= start_utc)
            .group_by(day_col)
        )).all()
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


@router.get("/me/status")
async def get_seller_status(
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == current_user.id)
    )
    profile = result.first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    return {
        "verification_status": profile.verification_status,
        "rejection_reason": profile.rejection_reason,
    }


@router.get("/me/profile", response_model=SellerProfilePayload)
async def get_seller_profile(
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> SellerProfilePayload:
    assert current_user.id is not None
    profile = await _seller_profile_with_address(session, current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    assert profile.id is not None
    services = await list_profile_services(session, profile.id)
    return SellerProfilePayload(
        id=profile.id,
        user_id=profile.user_id,
        full_name=compose_full_name(profile.first_name, profile.last_name),
        business_name=profile.business_name,
        services=services,
        address=address_to_payload(profile.business_address),
        phone=profile.phone,
        gst_number=profile.gst_number,
        fssai_license=profile.fssai_license,
        bank_account_number=profile.bank_account_number,
        bank_ifsc=profile.bank_ifsc,
        verification_status=profile.verification_status.value,
        rejection_reason=profile.rejection_reason,
    )


@router.patch("/me/profile")
async def update_seller_profile(
    body: SellerProfileUpdateBody,
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    assert current_user.id is not None
    profile = await _seller_profile_with_address(session, current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    if profile.verification_status is VerificationStatus.Approved:
        # Approved sellers must route profile edits through the change-request
        # workflow. Pending / Rejected sellers can still patch directly so they
        # can iterate on a rejected application.
        raise HTTPException(status_code=409, detail="use_change_request")

    if body.service_ids is not None:
        if profile.verification_status == VerificationStatus.Approved:
            raise HTTPException(
                status_code=400, detail="Services are locked after approval"
            )
        try:
            valid_ids = await validate_service_ids(session, body.service_ids)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await replace_profile_services(session, profile, valid_ids)

    if body.full_name is not None:
        first_name, last_name = split_full_name(body.full_name)
        profile.first_name = first_name
        profile.last_name = last_name
    profile.business_name = body.business_name
    profile.phone = body.phone
    profile.gst_number = body.gst_number or None
    profile.fssai_license = body.fssai_license or None
    profile.bank_account_number = body.bank_account_number or None
    profile.bank_ifsc = body.bank_ifsc or None

    address = profile.business_address
    for key, value in address_from_payload(body.address).items():
        setattr(address, key, value)

    # Capture status BEFORE the unconditional Pending reset so we can detect
    # an actual state transition (Rejected/Approved → Pending = resubmit).
    previous_status = profile.verification_status
    profile.verification_status = VerificationStatus.Pending
    profile.rejection_reason = None

    await session.commit()
    await session.refresh(profile)

    is_resubmit = previous_status != VerificationStatus.Pending
    if is_resubmit and profile.id is not None:
        dispatch_seller_application_submitted(profile.id)

    return {
        "verification_status": profile.verification_status,
        "rejection_reason": profile.rejection_reason,
    }


@router.patch("/me/services/{service_id}", response_model=ServicePayload)
async def set_my_service_min_order_value(
    service_id: int,
    body: SetServiceMinOrderValueBody,
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ServicePayload:
    assert current_user.id is not None
    profile = await _seller_profile_with_address(session, current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    if profile.verification_status is VerificationStatus.Approved:
        raise HTTPException(status_code=409, detail="use_change_request")
    assert profile.id is not None
    profile_id: int = profile.id
    row = (await session.exec(
        select(SellerProfileService).where(
            SellerProfileService.seller_profile_id == profile_id,
            SellerProfileService.service_id == service_id,
        )
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Service not offered by this seller")
    row.min_order_value = body.min_order_value
    if body.delivery_eta_min_minutes is not None and body.delivery_eta_max_minutes is not None:
        row.delivery_eta_min_minutes = body.delivery_eta_min_minutes
        row.delivery_eta_max_minutes = body.delivery_eta_max_minutes
    session.add(row)
    await session.commit()
    services = await list_profile_services(session, profile_id)
    payload = next((s for s in services if s.id == service_id), None)
    assert payload is not None
    return payload


@router.patch("/me/store/pause", response_model=StoreRead)
async def pause_my_store(
    body: StorePauseBody,
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(get_request_locale),
) -> StoreRead:
    from app.api.stores import _store_read

    assert current_user.id is not None
    store = await _seller_store(session, current_user.id)
    await set_store_pause(
        session, store,
        is_paused=body.is_paused, reason=body.reason, paused_until=body.paused_until,
    )
    await session.commit()
    await session.refresh(store)
    return await _store_read(session, store, lang)


@router.patch("/me/services/{service_id}/pause", response_model=ServicePayload)
async def pause_my_service(
    service_id: int,
    body: StorePauseBody,
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ServicePayload:
    assert current_user.id is not None
    profile = await _seller_profile_with_address(session, current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    assert profile.id is not None
    profile_id: int = profile.id
    await set_service_pause(
        session, seller_profile_id=profile_id, service_id=service_id,
        is_paused=body.is_paused, reason=body.reason, paused_until=body.paused_until,
    )
    await session.commit()
    services = await list_profile_services(session, profile_id)
    payload = next((s for s in services if s.id == service_id), None)
    assert payload is not None
    return payload


class AdminVerifyBody(BaseModel):
    action: str
    rejection_reason: Optional[str] = None


async def _notify_seller_of_decision(
    session: AsyncSession, seller_id: int, profile: SellerProfile
) -> None:
    user = (await session.exec(
        select(User).where(User.id == seller_id)
    )).first()
    if not user or not user.email:
        return
    if profile.verification_status == VerificationStatus.Approved:
        dispatch_seller_approved(user.email, profile.business_name)
    elif profile.verification_status == VerificationStatus.Rejected:
        dispatch_seller_rejected(
            user.email, profile.business_name, profile.rejection_reason or ""
        )


@router.get("/me/eligible-products", response_model=List[EligibleProduct])
async def list_my_eligible_products(
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
    lang: str = Depends(get_request_locale),
) -> List[EligibleProduct]:
    profile_result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == seller.id)
    )
    profile = profile_result.first()
    if profile is None or profile.id is None:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    store_result = await session.exec(
        select(Store).where(Store.seller_profile_id == profile.id)
    )
    store = store_result.first()
    if store is None or store.id is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "STORE_NOT_PROVISIONED", "message": "No store yet"},
        )

    return await list_eligible_products(
        session, profile_id=profile.id, store_id=store.id, lang=lang
    )


@router.patch("/admin/{seller_id}/verify")
async def admin_verify_seller(
    seller_id: int,
    body: AdminVerifyBody,
    _current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == seller_id)
    )
    profile = result.first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    if body.action == "approve":
        # Guard: profile must have at least one service
        service_count = (await session.exec(
            select(func.count()).where(
                SellerProfileService.seller_profile_id == profile.id
            )
        )).one()
        if int(service_count) == 0:
            raise HTTPException(
                status_code=400, detail="Set services before approving"
            )

        profile.verification_status = VerificationStatus.Approved
        profile.rejection_reason = None

        # Idempotent store provisioning
        existing_store = (await session.exec(
            select(Store).where(Store.seller_profile_id == profile.id)
        )).first()
        # Note: Store.address is captured at first approval. Subsequent
        # business-address edits do not propagate to an existing Store —
        # sellers update store address via a dedicated store-settings flow.
        if existing_store is None:
            biz_addr = (await session.exec(
                select(Address).where(Address.id == profile.business_address_id)
            )).first()
            if biz_addr is None:
                raise HTTPException(
                    status_code=500, detail="Seller profile missing business address"
                )
            store_addr = Address(
                address_line1=biz_addr.address_line1,
                address_line2=biz_addr.address_line2,
                landmark=biz_addr.landmark,
                city=biz_addr.city,
                state=biz_addr.state,
                pincode=biz_addr.pincode,
                country=biz_addr.country,
                latitude=biz_addr.latitude,
                longitude=biz_addr.longitude,
                digipin=biz_addr.digipin,
                place_id=biz_addr.place_id,
                location_source=biz_addr.location_source,
            )
            session.add(store_addr)
            await session.flush()
            # If the seller pinned their location during signup (lat/lng set
            # AND source is 'pin' or 'autocomplete'), the auto-created Store
            # inherits a confirmed pin. Otherwise the seller has to confirm
            # via the dashboard banner.
            inherits_pin = (
                biz_addr.latitude is not None
                and biz_addr.longitude is not None
                and biz_addr.location_source in (
                    LocationSource.pin, LocationSource.autocomplete,
                )
            )
            session.add(Store(
                name=profile.business_name,
                is_active=True,
                seller_profile_id=profile.id,
                address_id=store_addr.id,
                pin_confirmed=inherits_pin,
            ))
    elif body.action == "reject":
        if not body.rejection_reason or not body.rejection_reason.strip():
            raise HTTPException(status_code=400, detail="rejection_reason required when rejecting")
        profile.verification_status = VerificationStatus.Rejected
        profile.rejection_reason = body.rejection_reason
    else:
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # Another approval won the race; re-fetch and return success.
        refreshed = await session.exec(
            select(SellerProfile).where(SellerProfile.user_id == seller_id)
        )
        profile = refreshed.first()
        assert profile is not None
    await session.refresh(profile)

    await _notify_seller_of_decision(session, seller_id, profile)

    return {
        "seller_id": seller_id,
        "verification_status": profile.verification_status,
        "rejection_reason": profile.rejection_reason,
    }


ALLOWED_STATUSES = {"pending", "approved", "rejected", "all"}


# Performance note: list_profile_services issues one query per profile.
# For small admin queues this is fine; if listings grow or pagination lands,
# rewrite to a single JOIN across SellerProfile / SellerProfileService /
# Service / ServiceTranslation with selectinload-style batching.
async def _application_payload(
    session: AsyncSession,
    profile: SellerProfile,
    user: User,
    address: Address,
) -> dict:  # type: ignore[type-arg]
    assert profile.id is not None
    services = await list_profile_services(session, profile.id)
    return SellerApplicationPayload(
        seller_id=user.id,
        email=user.email,
        full_name=compose_full_name(profile.first_name, profile.last_name),
        business_name=profile.business_name,
        services=services,
        address=address_to_payload(address),
        phone=profile.phone,
        gst_number=profile.gst_number,
        fssai_license=profile.fssai_license,
        bank_account_number=profile.bank_account_number,
        bank_ifsc=profile.bank_ifsc,
        verification_status=profile.verification_status.value,
        rejection_reason=profile.rejection_reason,
        submitted_at=profile.created_at.isoformat() if profile.created_at else None,
        updated_at=profile.updated_at.isoformat() if profile.updated_at else None,
    ).model_dump()


@router.get("/admin/applications", response_model=PagedResponse[dict])  # type: ignore[type-arg]
async def admin_list_applications(
    status: str = "pending",
    q: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> PagedResponse:  # type: ignore[type-arg]
    if status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    stmt = (
        select(SellerProfile, User, Address)
        .join(User, User.id == SellerProfile.user_id)  # type: ignore[arg-type]
        .join(Address, Address.id == SellerProfile.business_address_id)  # type: ignore[arg-type]
    )
    if status != "all":
        stmt = stmt.where(SellerProfile.verification_status == VerificationStatus(status))
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                SellerProfile.business_name.ilike(like),  # type: ignore[attr-defined]
                SellerProfile.phone.ilike(like),  # type: ignore[attr-defined]
                SellerProfile.first_name.ilike(like),  # type: ignore[attr-defined]
                SellerProfile.last_name.ilike(like),  # type: ignore[attr-defined]
                User.email.ilike(like),  # type: ignore[attr-defined]
            )
        )
    stmt = stmt.order_by(desc(SellerProfile.created_at))  # type: ignore[arg-type]

    total = int((await session.exec(select(func.count()).select_from(stmt.subquery()))).one())

    rows = (await session.exec(stmt.offset((page - 1) * page_size).limit(page_size))).all()
    items = [
        await _application_payload(session, profile, user, address)
        for profile, user, address in rows
    ]
    return PagedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/admin/applications/counts")
async def admin_application_counts(
    _current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    stmt = select(
        SellerProfile.verification_status,
        func.count(SellerProfile.id),  # type: ignore[arg-type]
    ).group_by(SellerProfile.verification_status)
    result = await session.exec(stmt)
    rows = result.all()

    counts = {"pending": 0, "approved": 0, "rejected": 0}
    for status_value, count in rows:
        key = status_value.value if hasattr(status_value, "value") else str(status_value)
        if key in counts:
            counts[key] = count
    counts["total"] = counts["pending"] + counts["approved"] + counts["rejected"]
    return counts


@router.patch("/admin/{seller_id}/services")
async def admin_set_services(
    seller_id: int,
    body: AdminSetServicesBody,
    current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    profile_result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == seller_id)
    )
    profile = profile_result.first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    assert profile.id is not None
    assert current_user.id is not None
    profile_id: int = profile.id

    # If the admin is overriding services directly, supersede any open
    # change-request for the Services group so its now-stale baseline can't
    # be applied later by an approval click.
    await supersede_open_cr(
        session=session,
        seller_profile_id=profile_id,
        group=SellerProfileChangeGroup.Services,
        admin_user_id=current_user.id,
        action_name="admin_set_services",
    )

    try:
        valid_ids = await validate_service_ids(session, body.service_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await replace_profile_services(session, profile, valid_ids)
    await session.commit()
    services = await list_profile_services(session, profile_id)
    return {"seller_id": seller_id, "services": [s.model_dump() for s in services]}


@router.patch("/admin/{seller_id}/services/{service_id}", response_model=ServicePayload)
async def admin_set_service_min_order_value(
    seller_id: int,
    service_id: int,
    body: SetServiceMinOrderValueBody,
    current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ServicePayload:
    assert current_user.id is not None
    profile = (await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == seller_id)
    )).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    if profile.verification_status != VerificationStatus.Approved:
        raise HTTPException(status_code=409, detail="seller_not_active")
    assert profile.id is not None
    profile_id: int = profile.id
    # Supersede any open Services-group CR — the admin's direct edit drifts
    # the baseline these CRs were submitted against.
    await supersede_open_cr(
        session=session,
        seller_profile_id=profile_id,
        group=SellerProfileChangeGroup.Services,
        admin_user_id=current_user.id,
        action_name="admin_set_service_min_order_value",
    )
    row = (await session.exec(
        select(SellerProfileService).where(
            SellerProfileService.seller_profile_id == profile_id,
            SellerProfileService.service_id == service_id,
        )
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Service not offered by this seller")
    before = {
        "min_order_value": row.min_order_value,
        "delivery_eta_min_minutes": row.delivery_eta_min_minutes,
        "delivery_eta_max_minutes": row.delivery_eta_max_minutes,
    }
    row.min_order_value = body.min_order_value
    if body.delivery_eta_min_minutes is not None and body.delivery_eta_max_minutes is not None:
        row.delivery_eta_min_minutes = body.delivery_eta_min_minutes
        row.delivery_eta_max_minutes = body.delivery_eta_max_minutes
    session.add(row)
    await admin_audit.log(
        session=session,
        admin_user_id=current_user.id,
        target_seller_id=profile_id,
        target_type=AdminActionTargetType.SellerProfile,
        target_id=profile_id,
        action="service.set_min_order_value",
        before_json={"service_id": service_id, **before},
        after_json={
            "service_id": service_id,
            "min_order_value": body.min_order_value,
            "delivery_eta_min_minutes": row.delivery_eta_min_minutes,
            "delivery_eta_max_minutes": row.delivery_eta_max_minutes,
        },
    )
    await session.commit()
    services = await list_profile_services(session, profile_id)
    payload = next((s for s in services if s.id == service_id), None)
    assert payload is not None
    return payload


@router.patch("/admin/{seller_id}/store/pause", response_model=StoreRead)
async def admin_pause_store(
    seller_id: int,
    body: StorePauseBody,
    current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(get_request_locale),
) -> StoreRead:
    from app.api.stores import _store_read

    assert current_user.id is not None
    profile = (await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == seller_id)
    )).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    if profile.verification_status != VerificationStatus.Approved:
        raise HTTPException(status_code=409, detail="seller_not_active")
    store = (await session.exec(
        select(Store)
        .where(Store.seller_profile_id == profile.id)
        .options(
            selectinload(Store.address),  # type: ignore[arg-type]
            selectinload(Store.seller_profile),  # type: ignore[arg-type]
        )
    )).first()
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    await set_store_pause(
        session, store,
        is_paused=body.is_paused, reason=body.reason, paused_until=body.paused_until,
        acting_admin_id=current_user.id,
    )
    await session.commit()
    await session.refresh(store)
    return await _store_read(session, store, lang)


@router.patch("/admin/{seller_id}/services/{service_id}/pause", response_model=ServicePayload)
async def admin_pause_service(
    seller_id: int,
    service_id: int,
    body: StorePauseBody,
    current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ServicePayload:
    assert current_user.id is not None
    profile = (await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == seller_id)
    )).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    if profile.verification_status != VerificationStatus.Approved:
        raise HTTPException(status_code=409, detail="seller_not_active")
    assert profile.id is not None
    profile_id: int = profile.id
    await set_service_pause(
        session, seller_profile_id=profile_id, service_id=service_id,
        is_paused=body.is_paused, reason=body.reason, paused_until=body.paused_until,
        acting_admin_id=current_user.id,
    )
    await session.commit()
    services = await list_profile_services(session, profile_id)
    payload = next((s for s in services if s.id == service_id), None)
    assert payload is not None
    return payload
