from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin, get_current_seller
from app.db.session import get_db_session
from app.models.address import Address
from app.models.base import User
from app.models.profile import SellerProfile, VerificationStatus
from app.schemas.address import address_from_payload, address_to_payload
from app.schemas.sellers import (
    SellerApplicationPayload,
    SellerProfilePayload,
    SellerProfileUpdateBody,
)
from app.services.profiles import compose_full_name, split_full_name

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
    profile = await _seller_profile_with_address(session, current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    return SellerProfilePayload(
        id=profile.id,
        user_id=profile.user_id,
        full_name=compose_full_name(profile.first_name, profile.last_name),
        business_name=profile.business_name,
        business_category=profile.business_category,
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
    profile = await _seller_profile_with_address(session, current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    if body.full_name is not None:
        first_name, last_name = split_full_name(body.full_name)
        profile.first_name = first_name
        profile.last_name = last_name
    profile.business_name = body.business_name
    profile.business_category = body.business_category
    profile.phone = body.phone
    profile.gst_number = body.gst_number
    profile.fssai_license = body.fssai_license
    profile.bank_account_number = body.bank_account_number
    profile.bank_ifsc = body.bank_ifsc

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
        profile.verification_status = VerificationStatus.Approved
        profile.rejection_reason = None
    elif body.action == "reject":
        if not body.rejection_reason or not body.rejection_reason.strip():
            raise HTTPException(status_code=400, detail="rejection_reason required when rejecting")
        profile.verification_status = VerificationStatus.Rejected
        profile.rejection_reason = body.rejection_reason
    else:
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    await session.commit()
    await session.refresh(profile)
    return {
        "seller_id": seller_id,
        "verification_status": profile.verification_status,
        "rejection_reason": profile.rejection_reason,
    }


ALLOWED_STATUSES = {"pending", "approved", "rejected", "all"}


def _application_payload(profile: SellerProfile, user: User, address: Address) -> dict:  # type: ignore[type-arg]
    return SellerApplicationPayload(
        seller_id=user.id,
        email=user.email,
        full_name=compose_full_name(profile.first_name, profile.last_name),
        business_name=profile.business_name,
        business_category=profile.business_category,
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
    return [_application_payload(profile, user, address) for profile, user, address in rows]


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
