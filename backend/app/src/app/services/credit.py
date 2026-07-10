# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Credit-customers service: admin config, grant/adjust/repayment ledger,
checkout charge/reversal, and eligibility. The platform is a ledger +
enforcement layer only — no money moves for credit."""
from typing import Optional

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.admin_audit import AdminActionTargetType
from app.models.credit import SellerCreditConfig
from app.services import admin_audit

# ─── Admin per-seller config ─────────────────────────────────────────────


async def load_seller_credit_config(
    session: AsyncSession, seller_profile_id: int
) -> SellerCreditConfig:
    """The seller's config row, or a transient default (unsaved) if none yet."""
    row = (
        await session.exec(
            select(SellerCreditConfig).where(
                SellerCreditConfig.seller_profile_id == seller_profile_id
            )
        )
    ).first()
    return row or SellerCreditConfig(seller_profile_id=seller_profile_id)


async def get_or_create_seller_credit_config(
    session: AsyncSession, seller_profile_id: int
) -> SellerCreditConfig:
    row = (
        await session.exec(
            select(SellerCreditConfig).where(
                SellerCreditConfig.seller_profile_id == seller_profile_id
            )
        )
    ).first()
    if row is None:
        row = SellerCreditConfig(seller_profile_id=seller_profile_id)
        session.add(row)
        await session.flush()
    return row


async def admin_set_credit_config(
    session: AsyncSession,
    *,
    seller_profile_id: int,
    admin_user_id: int,
    credit_enabled: Optional[bool] = None,
    max_limit_per_customer: Optional[float] = None,
) -> SellerCreditConfig:
    row = await get_or_create_seller_credit_config(session, seller_profile_id)
    before = {
        "credit_enabled": row.credit_enabled,
        "max_limit_per_customer": row.max_limit_per_customer,
    }
    if credit_enabled is not None:
        row.credit_enabled = credit_enabled
    if max_limit_per_customer is not None:
        if max_limit_per_customer < 0:
            raise HTTPException(status_code=422, detail={"error": "invalid_cap"})
        row.max_limit_per_customer = max_limit_per_customer
    session.add(row)
    await session.flush()
    await admin_audit.log(
        session=session,
        admin_user_id=admin_user_id,
        target_seller_id=seller_profile_id,
        target_type=AdminActionTargetType.SellerProfile,
        target_id=seller_profile_id,
        action="credit.set_config",
        before_json=before,
        after_json={
            "credit_enabled": row.credit_enabled,
            "max_limit_per_customer": row.max_limit_per_customer,
        },
    )
    await session.commit()
    await session.refresh(row)
    return row
