from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin, get_current_seller
from app.db.session import get_db_session
from app.models.base import User
from app.models.seller import SellerProfile, VerificationStatus

router = APIRouter()


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


@router.get("/me/profile")
async def get_seller_profile(
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == current_user.id)
    )
    profile = result.first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    return profile.model_dump()


class SellerProfileUpdateBody(BaseModel):
    business_name: str
    business_category: str
    address: str
    phone: str
    gst_number: str
    fssai_license: str
    bank_account_number: str
    bank_ifsc: str


@router.patch("/me/profile")
async def update_seller_profile(
    body: SellerProfileUpdateBody,
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == current_user.id)
    )
    profile = result.first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    profile.business_name = body.business_name
    profile.business_category = body.business_category
    profile.address = body.address
    profile.phone = body.phone
    profile.gst_number = body.gst_number
    profile.fssai_license = body.fssai_license
    profile.bank_account_number = body.bank_account_number
    profile.bank_ifsc = body.bank_ifsc
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
