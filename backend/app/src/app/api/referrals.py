# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db_session
from app.models.base import User
from app.models.referral import Referral, ReferralStatus
from app.schemas.pagination import PagedResponse
from app.schemas.referrals import ReferralCreate, ReferralRead
from app.services import referrals as svc

router = APIRouter()
# Admin queue/approve/reject/settings routes are attached in this same module
# (see below); mounted under `/admin` in api/__init__.py.
admin_router = APIRouter()


@router.post("", response_model=ReferralRead, status_code=status.HTTP_201_CREATED)
async def submit_referral(
    body: ReferralCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReferralRead:
    try:
        row = await svc.create_referral(
            session,
            source_user_id=int(current_user.id),  # type: ignore[arg-type]
            source_role=current_user.role,
            payload=body,
        )
    except svc.DuplicateContact as exc:
        raise HTTPException(status_code=409, detail={"error": exc.reason}) from exc
    # If approval is disabled the row is already `approved` — issue the invite now.
    if row.status == ReferralStatus.approved:
        await svc.issue_invite_and_dispatch(session, referral=row)
    await session.commit()
    await session.refresh(row)
    return ReferralRead.model_validate(row)


@router.get("", response_model=PagedResponse[ReferralRead])
async def list_my_referrals(
    status_filter: Optional[ReferralStatus] = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PagedResponse[ReferralRead]:
    rows = await svc.list_referrals_for_user(
        session, user_id=int(current_user.id), status=status_filter  # type: ignore[arg-type]
    )
    items = [ReferralRead.model_validate(r) for r in rows]
    return PagedResponse(items=items, total=len(items), page=1, page_size=len(items) or 1)


@router.get("/{referral_id}", response_model=ReferralRead)
async def get_my_referral(
    referral_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReferralRead:
    row = await session.get(Referral, referral_id)
    if row is None or row.source_user_id != int(current_user.id):  # type: ignore[arg-type]
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return ReferralRead.model_validate(row)
