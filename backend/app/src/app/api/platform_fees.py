# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin platform-fee configuration.

`admin_router` mounted at /api/v1/admin. Global settings + per-service fee config
+ subscription-plan pricing."""
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.base import User
from app.models.platform_fee import PlatformFeeSettings
from app.schemas.platform_fees import (
    PlatformFeeSettingsPatch,
    PlatformFeeSettingsRead,
)
from app.services import platform_fees as fees

admin_router = APIRouter()


def _settings_read(s: PlatformFeeSettings) -> PlatformFeeSettingsRead:
    return PlatformFeeSettingsRead(
        grace_period_days=s.grace_period_days,
        expiry_reminder_start_days=s.expiry_reminder_start_days,
        pending_payment_protect_days=s.pending_payment_protect_days,
        bank_account_name=s.bank_account_name,
        bank_account_number=s.bank_account_number,
        bank_ifsc=s.bank_ifsc,
        upi_id=s.upi_id,
        qr_image_url=s.qr_image_url,
        gstin=s.gstin,
    )


@admin_router.get("/fees/settings", response_model=PlatformFeeSettingsRead)
async def get_fee_settings(
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformFeeSettingsRead:
    return _settings_read(await fees.load_settings(session))


@admin_router.patch("/fees/settings", response_model=PlatformFeeSettingsRead)
async def patch_fee_settings(
    body: PlatformFeeSettingsPatch,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformFeeSettingsRead:
    row = await fees.get_or_create_settings(session)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _settings_read(row)
