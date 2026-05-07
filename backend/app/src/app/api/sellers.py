from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.locale import get_request_locale
from app.core.security import get_current_admin, get_current_seller
from app.db.session import get_db_session
from app.models.address import Address, LocationSource
from app.models.base import User
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from app.models.store import Store
from app.schemas.address import address_from_payload, address_to_payload
from app.schemas.inventory import EligibleProduct
from app.schemas.sellers import (
    AdminSetServicesBody,
    SellerApplicationPayload,
    SellerProfilePayload,
    SellerProfileUpdateBody,
)
from app.services.eligible_products import list_eligible_products
from app.services.profiles import compose_full_name, split_full_name
from app.services.seller_emails import (
    dispatch_seller_approved,
    dispatch_seller_rejected,
)
from app.services.seller_services import (
    list_profile_services,
    replace_profile_services,
    validate_service_ids,
)

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

    profile.verification_status = VerificationStatus.Pending
    profile.rejection_reason = None

    await session.commit()
    await session.refresh(profile)
    return {
        "verification_status": profile.verification_status,
        "rejection_reason": profile.rejection_reason,
    }


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


@router.get("/admin/applications")
async def admin_list_applications(
    status: str = "pending",
    _current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> List[dict]:  # type: ignore[type-arg]
    if status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    stmt = (
        select(SellerProfile, User, Address)
        .join(User, User.id == SellerProfile.user_id)  # type: ignore[arg-type]
        .join(Address, Address.id == SellerProfile.business_address_id)  # type: ignore[arg-type]
    )
    if status != "all":
        stmt = stmt.where(SellerProfile.verification_status == VerificationStatus(status))
    stmt = stmt.order_by(desc(SellerProfile.created_at))  # type: ignore[arg-type]

    result = await session.exec(stmt)
    rows = result.all()
    return [
        await _application_payload(session, profile, user, address)
        for profile, user, address in rows
    ]


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
    _current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    profile_result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == seller_id)
    )
    profile = profile_result.first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    assert profile.id is not None
    profile_id: int = profile.id

    try:
        valid_ids = await validate_service_ids(session, body.service_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await replace_profile_services(session, profile, valid_ids)
    await session.commit()
    services = await list_profile_services(session, profile_id)
    return {"seller_id": seller_id, "services": [s.model_dump() for s in services]}
