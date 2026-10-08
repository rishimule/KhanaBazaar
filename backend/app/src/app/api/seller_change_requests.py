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
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_seller
from app.db.session import get_db_session
from app.models.base import User
from app.models.profile import SellerProfile
from app.models.seller_profile_change_request import (
    SellerProfileChangeGroup,
    SellerProfileChangeRequest,
    SellerProfileChangeRequestEvent,
)
from app.schemas.seller_profile_change_request import (
    ChangeRequestCreateBody,
    ChangeRequestEventRead,
    ChangeRequestRead,
    ChangeRequestResubmitBody,
)
from app.services.payment_methods import set_upi_enabled
from app.services.seller_profile_change_requests import (
    OPEN_STATUSES,
    create_avatar_change_request,
    create_change_request,
    create_payments_qr_change_request,
    create_store_logo_change_request,
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


# Upload-backed groups: the image url field, and the 422 code naming the
# multipart route that must carry the image.
_IMAGE_FIELDS: dict[SellerProfileChangeGroup, tuple[str, str]] = {
    SellerProfileChangeGroup.Avatar: ("avatar_url", "avatar_upload_required"),
    SellerProfileChangeGroup.StoreLogo: ("logo_url", "store_logo_upload_required"),
    SellerProfileChangeGroup.Payments: ("upi_qr_url", "upi_qr_upload_required"),
}


def _reject_forged_image(group: SellerProfileChangeGroup, proposed: dict) -> None:
    """Guard the generic JSON CR path: avatar / store-logo / payments-QR
    *uploads* must go through their dedicated multipart routes
    (`POST /me/avatar`, `POST /me/store/logo`, `POST /me/payments/qr`), which
    produce a trusted, owner-scoped storage_key.

    The generic endpoint only permits *removal* (empty url) and never takes a
    storage_key: a caller-chosen key could name another owner's blob, which
    withdrawing or rejecting the request would then delete.
    """
    image = _IMAGE_FIELDS.get(group)
    if image is None:
        return
    url_field, code = image
    if (proposed.get(url_field) or "") or (proposed.get("storage_key") or ""):
        raise HTTPException(status_code=422, detail=code)


def _require_upi_vpa(group: SellerProfileChangeGroup, proposed: dict[str, Any]) -> None:
    """A seller's payments request must name a UPI ID. An empty one validates
    as "no UPI ID, UPI off" and would wipe the live payee on approval (the old
    Edit-button trap, spec 2026-10-07 §4). Turning UPI off is the instant
    switch, not a request; an admin can still clear an ID deliberately through
    approve-with-edits."""
    if group is SellerProfileChangeGroup.Payments and not str(
        proposed.get("upi_vpa") or ""
    ).strip():
        raise HTTPException(status_code=422, detail="upi_vpa_required")


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
    _reject_forged_image(body.group, body.proposed)
    _require_upi_vpa(body.group, body.proposed)
    profile = await _seller_profile_or_404(session, seller)
    res = await create_change_request(
        session=session,
        seller_profile=profile,
        group=body.group,
        proposed=body.proposed,
        note=body.note,
        actor_user_id=seller.id,
        phone_change_token=body.phone_change_token,
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
    _reject_forged_image(cr.group, body.proposed)
    _require_upi_vpa(cr.group, body.proposed)
    proposed = dict(body.proposed)
    if cr.group in _IMAGE_FIELDS:
        # A resubmission can't carry an image, so the blob stays the one filed
        # with this request (server-stored, so not forgeable) and its cleanup
        # still finds it. The generic edit form can't re-upload the payments
        # verification QR either, so that request keeps its QR too.
        proposed["storage_key"] = cr.proposed_json.get("storage_key")
        if cr.group is SellerProfileChangeGroup.Payments:
            proposed["upi_qr_url"] = cr.proposed_json.get("upi_qr_url") or ""
    res = await resubmit(
        session=session,
        cr=cr,
        seller_profile=profile,
        proposed=proposed,
        note=body.note,
        actor_user_id=seller.id,
        phone_change_token=body.phone_change_token,
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


@router.post("/me/avatar", response_model=ChangeRequestRead, status_code=201)
async def upload_my_avatar(
    file: UploadFile = File(...),
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ChangeRequestRead:
    assert seller.id is not None
    profile = await _seller_profile_or_404(session, seller)
    raw = await file.read()
    res = await create_avatar_change_request(
        session=session,
        seller_profile=profile,
        raw=raw,
        actor_user_id=seller.id,
    )
    await session.commit()
    await session.refresh(res.cr)
    for cb in res.emails:
        cb()
    return await _attach_events(session, res.cr)


@router.post("/me/store/logo", response_model=ChangeRequestRead, status_code=201)
async def upload_my_store_logo(
    file: UploadFile = File(...),
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ChangeRequestRead:
    assert seller.id is not None
    profile = await _seller_profile_or_404(session, seller)
    raw = await file.read()
    res = await create_store_logo_change_request(
        session=session,
        seller_profile=profile,
        raw=raw,
        actor_user_id=seller.id,
    )
    await session.commit()
    await session.refresh(res.cr)
    for cb in res.emails:
        cb()
    return await _attach_events(session, res.cr)


@router.post("/me/payments/qr", response_model=ChangeRequestRead, status_code=201)
async def upload_my_payments_qr(
    upi_vpa: str = Form(...),
    file: UploadFile = File(...),
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ChangeRequestRead:
    """Submit a UPI payee with a verification QR image for admin review.

    `upi_vpa` is the authoritative payee; the image is only so the reviewer can
    confirm the two agree. Format validation happens inside the CR payload
    schema, so a malformed VPA 422s before the blob is stored.
    """
    assert seller.id is not None
    profile = await _seller_profile_or_404(session, seller)
    raw = await file.read()
    res = await create_payments_qr_change_request(
        session=session,
        seller_profile=profile,
        raw=raw,
        upi_vpa=upi_vpa,
        actor_user_id=seller.id,
    )
    await session.commit()
    await session.refresh(res.cr)
    for cb in res.emails:
        cb()
    return await _attach_events(session, res.cr)


@router.patch("/me/payments/disable")
async def disable_my_upi(
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    """Turn UPI off immediately — deliberately NOT moderated.

    A compromised UPI handle has to stop receiving money now, not after an
    admin review. Disabling only removes a payment option, so it carries none
    of the risk that makes *enabling* reviewable. Modelled on the direct pause
    routes. `upi_vpa` is retained, so switching UPI back on from the Payments
    page needs no fresh review. Goes through `set_upi_enabled`, so unpaid
    orders drop the payee they saved under the old generation.

    Idempotent: disabling an already-disabled payee is a 200 no-op. Kept for
    dashboard tabs opened before `PATCH /me/payments/methods` existed.
    """
    # Row-locked like every switch writer, so the UPI generation can't be
    # overwritten with a stale value (services/payment_methods.py).
    profile = (
        await session.exec(
            select(SellerProfile).where(SellerProfile.user_id == seller.id).with_for_update()
        )
    ).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="seller_profile_not_found")
    set_upi_enabled(profile, False)
    session.add(profile)
    await session.commit()
    return {"upi_enabled": False}
