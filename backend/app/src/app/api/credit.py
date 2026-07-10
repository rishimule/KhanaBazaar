# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.base import User
from app.schemas.credit import AdminCreditConfigPatch, CreditConfigRead
from app.services import credit as svc

admin_router = APIRouter()


@admin_router.get(
    "/sellers/{seller_id}/credit-config", response_model=CreditConfigRead
)
async def admin_get_credit_config(
    seller_id: int,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> CreditConfigRead:
    row = await svc.load_seller_credit_config(session, seller_id)
    return CreditConfigRead.model_validate(row)


@admin_router.patch(
    "/sellers/{seller_id}/credit-config", response_model=CreditConfigRead
)
async def admin_patch_credit_config(
    seller_id: int,
    body: AdminCreditConfigPatch,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> CreditConfigRead:
    assert admin.id is not None
    row = await svc.admin_set_credit_config(
        session,
        seller_profile_id=seller_id,
        admin_user_id=admin.id,
        credit_enabled=body.credit_enabled,
        max_limit_per_customer=body.max_limit_per_customer,
    )
    return CreditConfigRead.model_validate(row)
