# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Seller-facing change-request endpoints mounted under ``/api/v1/sellers``.

These routes let an Approved seller submit, withdraw, and resubmit per-group
change requests against their own profile. All writes go through the
state-machine service in :mod:`app.services.seller_profile_change_requests`;
the router just owns request shape, auth, ownership checks, and
post-commit email dispatch.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_seller
from app.db.session import get_db_session
from app.models.base import User
from app.models.profile import SellerProfile
from app.models.seller_profile_change_request import (
    SellerProfileChangeRequest,
    SellerProfileChangeRequestEvent,
)
from app.schemas.seller_profile_change_request import (
    ChangeRequestCreateBody,
    ChangeRequestEventRead,
    ChangeRequestRead,
    ChangeRequestResubmitBody,
)
from app.services.seller_profile_change_requests import (
    OPEN_STATUSES,
    create_change_request,
    resubmit,
    withdraw,
)

router = APIRouter()


async def _seller_profile_or_404(
    session: AsyncSession, user: User
) -> SellerProfile:
    # Eager-load business_address so _baseline_for_group(Address) can read it
    # without triggering lazy load in async context.
    from sqlalchemy.orm import selectinload

    profile = (
        await session.exec(
            select(SellerProfile)
            .where(SellerProfile.user_id == user.id)
            .options(selectinload(SellerProfile.business_address))  # type: ignore[arg-type]
        )
    ).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="seller_profile_not_found")
    return profile


async def _cr_owned_by(
    session: AsyncSession, cr_id: uuid.UUID, profile: SellerProfile
) -> SellerProfileChangeRequest:
    cr = (
        await session.exec(
            select(SellerProfileChangeRequest).where(
                SellerProfileChangeRequest.id == cr_id,
                SellerProfileChangeRequest.seller_profile_id == profile.id,
            )
        )
    ).first()
    if cr is None:
        raise HTTPException(status_code=404, detail="change_request_not_found")
    return cr


async def _attach_events(
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


@router.get("/me/change-requests", response_model=list[ChangeRequestRead])
async def list_my_change_requests(
    status: str = Query(default="open"),
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> list[ChangeRequestRead]:
    profile = await _seller_profile_or_404(session, seller)
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
    "/me/change-requests/{cr_id}", response_model=ChangeRequestRead
)
async def get_my_change_request(
    cr_id: uuid.UUID,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ChangeRequestRead:
    profile = await _seller_profile_or_404(session, seller)
    cr = await _cr_owned_by(session, cr_id, profile)
    return await _attach_events(session, cr)


@router.post(
    "/me/change-requests", response_model=ChangeRequestRead, status_code=201
)
async def create_my_change_request(
    body: ChangeRequestCreateBody,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ChangeRequestRead:
    profile = await _seller_profile_or_404(session, seller)
    res = await create_change_request(
        session=session,
        seller_profile=profile,
        group=body.group,
        proposed=body.proposed,
        note=body.note,
        actor_user_id=seller.id,
    )
    await session.commit()
    await session.refresh(res.cr)
    for cb in res.emails:
        cb()
    return await _attach_events(session, res.cr)


@router.patch(
    "/me/change-requests/{cr_id}/resubmit",
    response_model=ChangeRequestRead,
)
async def resubmit_my_change_request(
    cr_id: uuid.UUID,
    body: ChangeRequestResubmitBody,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ChangeRequestRead:
    profile = await _seller_profile_or_404(session, seller)
    cr = await _cr_owned_by(session, cr_id, profile)
    res = await resubmit(
        session=session,
        cr=cr,
        proposed=body.proposed,
        note=body.note,
        actor_user_id=seller.id,
    )
    await session.commit()
    await session.refresh(res.cr)
    for cb in res.emails:
        cb()
    return await _attach_events(session, res.cr)


@router.post(
    "/me/change-requests/{cr_id}/withdraw", response_model=ChangeRequestRead
)
async def withdraw_my_change_request(
    cr_id: uuid.UUID,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ChangeRequestRead:
    profile = await _seller_profile_or_404(session, seller)
    cr = await _cr_owned_by(session, cr_id, profile)
    res = await withdraw(
        session=session, cr=cr, actor_user_id=seller.id,
    )
    await session.commit()
    await session.refresh(res.cr)
    return await _attach_events(session, res.cr)
