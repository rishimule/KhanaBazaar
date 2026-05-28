# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""State machine + per-group appliers for seller profile change requests.

All admin-side service functions write an `AdminActionLog` row in the same
transaction as the mutation (atomic audit). Email dispatchers fire AFTER
the caller commits — service returns the CR row plus a list of email
callbacks the caller invokes post-commit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.admin_audit import AdminActionTargetType
from app.models.base import UserRole
from app.models.profile import (
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.seller_profile_change_request import (
    SellerProfileChangeEventKind,
    SellerProfileChangeGroup,
    SellerProfileChangeRequest,
    SellerProfileChangeRequestEvent,
    SellerProfileChangeStatus,
)
from app.models.store import Store
from app.schemas.address import AddressPayload, address_from_payload
from app.schemas.seller_profile_change_request import (
    validate_group_payload,
)
from app.services import admin_audit
from app.services.profiles import compose_full_name, split_full_name
from app.services.seller_services import (
    list_profile_services,
    replace_profile_services,
    validate_service_ids,
)

logger = logging.getLogger(__name__)

OPEN_STATUSES = (
    SellerProfileChangeStatus.Submitted,
    SellerProfileChangeStatus.ChangesRequested,
)


@dataclass
class CRMutationResult:
    cr: SellerProfileChangeRequest
    emails: list[Callable[[], None]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _baseline_for_group(
    session: AsyncSession,
    profile: SellerProfile,
    group: SellerProfileChangeGroup,
) -> dict[str, Any]:
    """Snapshot the seller's current values for the group, used as diff anchor."""
    if group is SellerProfileChangeGroup.Identity:
        return {
            "full_name": compose_full_name(profile.first_name, profile.last_name),
            "business_name": profile.business_name,
            "phone": profile.phone,
        }
    if group is SellerProfileChangeGroup.Address:
        addr = profile.business_address
        return {
            "address_line1": addr.address_line1,
            "address_line2": addr.address_line2,
            "landmark": addr.landmark,
            "city": addr.city,
            "state": addr.state,
            "pincode": addr.pincode,
            "country": addr.country,
            "latitude": addr.latitude,
            "longitude": addr.longitude,
            "place_id": addr.place_id,
            "location_source": (
                addr.location_source.value if addr.location_source else None
            ),
        }
    if group is SellerProfileChangeGroup.Legal:
        return {
            "gst_number": profile.gst_number,
            "fssai_license": profile.fssai_license,
        }
    if group is SellerProfileChangeGroup.Banking:
        return {
            "bank_account_number": profile.bank_account_number,
            "bank_ifsc": profile.bank_ifsc,
        }
    if group is SellerProfileChangeGroup.Services:
        rows = await list_profile_services(session, profile.id or 0)
        return {
            "services": [
                {"service_id": row.id, "min_order_value": row.min_order_value}
                for row in rows
            ],
        }
    if group is SellerProfileChangeGroup.StoreBasics:
        store = (
            await session.exec(
                select(Store).where(Store.seller_profile_id == profile.id)
            )
        ).first()
        if store is None:
            raise HTTPException(status_code=404, detail="store_not_found")
        return {
            "store_name": store.name,
            "delivery_radius_km": store.delivery_radius_km,
        }
    raise ValueError(f"unknown group {group}")


async def _open_cr_for_group(
    session: AsyncSession,
    seller_profile_id: int,
    group: SellerProfileChangeGroup,
) -> Optional[SellerProfileChangeRequest]:
    result = await session.exec(
        select(SellerProfileChangeRequest).where(
            SellerProfileChangeRequest.seller_profile_id == seller_profile_id,
            SellerProfileChangeRequest.group == group,
            SellerProfileChangeRequest.status.in_(OPEN_STATUSES),  # type: ignore[attr-defined]
        )
    )
    return result.first()


def _emit_event(
    *,
    session: AsyncSession,
    cr: SellerProfileChangeRequest,
    kind: SellerProfileChangeEventKind,
    actor_user_id: int,
    actor_role: UserRole,
    payload_json: Optional[dict[str, Any]] = None,
    note: Optional[str] = None,
) -> None:
    session.add(
        SellerProfileChangeRequestEvent(
            change_request_id=cr.id,
            kind=kind,
            actor_user_id=actor_user_id,
            actor_role=actor_role.value,
            payload_json=payload_json,
            note=note,
        )
    )


async def create_change_request(
    *,
    session: AsyncSession,
    seller_profile: SellerProfile,
    group: SellerProfileChangeGroup,
    proposed: dict[str, Any],
    note: Optional[str],
    actor_user_id: int,
) -> CRMutationResult:
    """Create a new open CR for `group`. Caller commits."""
    if seller_profile.verification_status is not VerificationStatus.Approved:
        raise HTTPException(status_code=409, detail="seller_not_active")
    assert seller_profile.id is not None

    canonical = validate_group_payload(group, proposed)

    existing = await _open_cr_for_group(session, seller_profile.id, group)
    if existing is not None:
        raise HTTPException(status_code=409, detail="cr_already_open")

    baseline = await _baseline_for_group(session, seller_profile, group)

    cr = SellerProfileChangeRequest(
        seller_profile_id=seller_profile.id,
        group=group,
        status=SellerProfileChangeStatus.Submitted,
        proposed_json=canonical,
        baseline_json=baseline,
        submission_count=1,
    )
    session.add(cr)
    await session.flush()  # populates cr.id

    _emit_event(
        session=session,
        cr=cr,
        kind=SellerProfileChangeEventKind.Submitted,
        actor_user_id=actor_user_id,
        actor_role=UserRole.Seller,
        payload_json=canonical,
        note=note,
    )

    logger.info(
        "cr.create cr_id=%s seller=%s group=%s",
        cr.id, seller_profile.id, group.value,
    )

    from app.services.seller_emails import (
        dispatch_seller_change_request_submitted,
    )
    return CRMutationResult(
        cr=cr,
        emails=[lambda: dispatch_seller_change_request_submitted(cr.id)],
    )


async def withdraw(
    *,
    session: AsyncSession,
    cr: SellerProfileChangeRequest,
    actor_user_id: int,
) -> CRMutationResult:
    if cr.status not in OPEN_STATUSES:
        raise HTTPException(status_code=409, detail="cr_not_open")
    cr.status = SellerProfileChangeStatus.Withdrawn
    cr.decided_at = _now()
    cr.decided_by_user_id = actor_user_id
    cr.updated_at = _now()
    session.add(cr)
    _emit_event(
        session=session, cr=cr,
        kind=SellerProfileChangeEventKind.Withdrawn,
        actor_user_id=actor_user_id, actor_role=UserRole.Seller,
    )
    logger.info("cr.withdraw cr_id=%s", cr.id)
    return CRMutationResult(cr=cr, emails=[])


async def resubmit(
    *,
    session: AsyncSession,
    cr: SellerProfileChangeRequest,
    proposed: dict[str, Any],
    note: Optional[str],
    actor_user_id: int,
) -> CRMutationResult:
    if cr.status is not SellerProfileChangeStatus.ChangesRequested:
        raise HTTPException(status_code=409, detail="cr_not_resubmittable")
    canonical = validate_group_payload(cr.group, proposed)
    cr.proposed_json = canonical
    cr.submission_count += 1
    cr.status = SellerProfileChangeStatus.Submitted
    cr.updated_at = _now()
    cr.admin_note = None
    session.add(cr)
    _emit_event(
        session=session, cr=cr,
        kind=SellerProfileChangeEventKind.Resubmitted,
        actor_user_id=actor_user_id, actor_role=UserRole.Seller,
        payload_json=canonical, note=note,
    )
    logger.info(
        "cr.resubmit cr_id=%s submission=%s", cr.id, cr.submission_count
    )
    from app.services.seller_emails import (
        dispatch_seller_change_request_submitted,
    )
    return CRMutationResult(
        cr=cr,
        emails=[lambda: dispatch_seller_change_request_submitted(cr.id)],
    )


async def request_changes(
    *,
    session: AsyncSession,
    cr: SellerProfileChangeRequest,
    admin_user_id: int,
    note: str,
) -> CRMutationResult:
    if cr.status is not SellerProfileChangeStatus.Submitted:
        raise HTTPException(status_code=409, detail="cr_not_actionable")
    if len(note.strip()) < 5:
        raise HTTPException(status_code=422, detail="note_required")
    cr.status = SellerProfileChangeStatus.ChangesRequested
    cr.admin_note = note
    cr.updated_at = _now()
    session.add(cr)
    _emit_event(
        session=session, cr=cr,
        kind=SellerProfileChangeEventKind.ChangesRequested,
        actor_user_id=admin_user_id, actor_role=UserRole.Admin,
        note=note,
    )
    await admin_audit.log(
        session=session,
        admin_user_id=admin_user_id,
        target_seller_id=cr.seller_profile_id,
        target_type=AdminActionTargetType.SellerProfile,
        target_id=cr.seller_profile_id,
        action="profile_cr_request_changes",
        before_json={
            "cr_id": str(cr.id),
            "group": cr.group.value,
            "proposed": cr.proposed_json,
        },
        after_json={"cr_id": str(cr.id), "group": cr.group.value},
        reason=note,
    )
    logger.info("cr.request_changes cr_id=%s", cr.id)
    from app.services.seller_emails import (
        dispatch_seller_change_request_changes_requested,
    )
    return CRMutationResult(
        cr=cr,
        emails=[lambda: dispatch_seller_change_request_changes_requested(cr.id)],
    )


async def reject(
    *,
    session: AsyncSession,
    cr: SellerProfileChangeRequest,
    admin_user_id: int,
    reason: str,
) -> CRMutationResult:
    if cr.status not in OPEN_STATUSES:
        raise HTTPException(status_code=409, detail="cr_not_actionable")
    if len(reason.strip()) < 5:
        raise HTTPException(status_code=422, detail="reason_required")
    cr.status = SellerProfileChangeStatus.Rejected
    cr.admin_note = reason
    cr.decided_at = _now()
    cr.decided_by_user_id = admin_user_id
    cr.updated_at = _now()
    session.add(cr)
    _emit_event(
        session=session, cr=cr,
        kind=SellerProfileChangeEventKind.Rejected,
        actor_user_id=admin_user_id, actor_role=UserRole.Admin,
        note=reason,
    )
    await admin_audit.log(
        session=session,
        admin_user_id=admin_user_id,
        target_seller_id=cr.seller_profile_id,
        target_type=AdminActionTargetType.SellerProfile,
        target_id=cr.seller_profile_id,
        action="profile_cr_reject",
        before_json={
            "cr_id": str(cr.id),
            "group": cr.group.value,
            "proposed": cr.proposed_json,
        },
        after_json={"cr_id": str(cr.id), "group": cr.group.value},
        reason=reason,
    )
    logger.info("cr.reject cr_id=%s", cr.id)
    from app.services.seller_emails import (
        dispatch_seller_change_request_rejected,
    )
    return CRMutationResult(
        cr=cr,
        emails=[lambda: dispatch_seller_change_request_rejected(cr.id)],
    )


# ─── Per-group appliers ─────────────────────────────────────────────────


async def _apply_identity(
    session: AsyncSession, profile: SellerProfile, payload: dict[str, Any]
) -> None:
    full_name = str(payload["full_name"])
    first, last = split_full_name(full_name)
    profile.first_name = first
    profile.last_name = last
    profile.business_name = str(payload["business_name"])
    profile.phone = str(payload["phone"])
    session.add(profile)


async def _apply_address(
    session: AsyncSession, profile: SellerProfile, payload: dict[str, Any]
) -> None:
    addr = profile.business_address
    address_payload = AddressPayload.model_validate(payload)
    fields = address_from_payload(address_payload)
    for k, v in fields.items():
        setattr(addr, k, v)
    session.add(addr)


async def _apply_legal(
    session: AsyncSession, profile: SellerProfile, payload: dict[str, Any]
) -> None:
    profile.gst_number = payload.get("gst_number") or None
    profile.fssai_license = payload.get("fssai_license") or None
    session.add(profile)


async def _apply_banking(
    session: AsyncSession, profile: SellerProfile, payload: dict[str, Any]
) -> None:
    profile.bank_account_number = payload.get("bank_account_number") or None
    profile.bank_ifsc = payload.get("bank_ifsc") or None
    session.add(profile)


async def _apply_services(
    session: AsyncSession, profile: SellerProfile, payload: dict[str, Any]
) -> None:
    rows = payload["services"]
    ids = [int(r["service_id"]) for r in rows]
    try:
        valid = await validate_service_ids(session, ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await replace_profile_services(session, profile, valid)
    # second pass: set min_order_value per row
    existing_rows = (
        await session.exec(
            select(SellerProfileService).where(
                SellerProfileService.seller_profile_id == profile.id
            )
        )
    ).all()
    by_id = {row.service_id: row for row in existing_rows}
    for r in rows:
        sid = int(r["service_id"])
        if sid in by_id:
            by_id[sid].min_order_value = float(r["min_order_value"])
            session.add(by_id[sid])


async def _apply_store_basics(
    session: AsyncSession, profile: SellerProfile, payload: dict[str, Any]
) -> None:
    store = (
        await session.exec(
            select(Store).where(Store.seller_profile_id == profile.id)
        )
    ).first()
    if store is None:
        raise HTTPException(status_code=404, detail="store_not_found")
    store.name = str(payload["store_name"])
    store.delivery_radius_km = float(payload["delivery_radius_km"])
    session.add(store)


GROUP_APPLIERS = {
    SellerProfileChangeGroup.Identity: _apply_identity,
    SellerProfileChangeGroup.Address: _apply_address,
    SellerProfileChangeGroup.Legal: _apply_legal,
    SellerProfileChangeGroup.Banking: _apply_banking,
    SellerProfileChangeGroup.Services: _apply_services,
    SellerProfileChangeGroup.StoreBasics: _apply_store_basics,
}


async def approve(
    *,
    session: AsyncSession,
    cr: SellerProfileChangeRequest,
    admin_user_id: int,
    applied: Optional[dict[str, Any]] = None,
    note: Optional[str] = None,
) -> CRMutationResult:
    if cr.status is not SellerProfileChangeStatus.Submitted:
        raise HTTPException(status_code=409, detail="cr_not_actionable")
    # Lock the row to defeat double-approve races.
    locked = (
        await session.exec(
            select(SellerProfileChangeRequest)
            .where(SellerProfileChangeRequest.id == cr.id)
            .with_for_update()
        )
    ).first()
    if locked is None or locked.status is not SellerProfileChangeStatus.Submitted:
        raise HTTPException(status_code=409, detail="cr_not_actionable")

    raw_applied = applied if applied is not None else cr.proposed_json
    try:
        canonical_applied = validate_group_payload(cr.group, raw_applied)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    profile = (
        await session.exec(
            select(SellerProfile).where(
                SellerProfile.id == cr.seller_profile_id
            )
        )
    ).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="seller_not_found")

    applier = GROUP_APPLIERS[cr.group]
    await applier(session, profile, canonical_applied)

    has_edits = canonical_applied != cr.proposed_json
    cr.status = SellerProfileChangeStatus.Approved
    cr.applied_json = canonical_applied
    cr.admin_note = note
    cr.decided_at = _now()
    cr.decided_by_user_id = admin_user_id
    cr.updated_at = _now()
    session.add(cr)

    event_payload: dict[str, Any] = {"applied": canonical_applied}
    if has_edits:
        event_payload["seller_proposed"] = cr.proposed_json
    _emit_event(
        session=session, cr=cr,
        kind=(
            SellerProfileChangeEventKind.ApprovedWithEdits if has_edits
            else SellerProfileChangeEventKind.Approved
        ),
        actor_user_id=admin_user_id, actor_role=UserRole.Admin,
        payload_json=event_payload,
        note=note,
    )

    audit_after: dict[str, Any] = {
        "cr_id": str(cr.id),
        "group": cr.group.value,
        "applied": canonical_applied,
    }
    if has_edits:
        audit_after["seller_proposed"] = cr.proposed_json
    await admin_audit.log(
        session=session,
        admin_user_id=admin_user_id,
        target_seller_id=cr.seller_profile_id,
        target_type=AdminActionTargetType.SellerProfile,
        target_id=cr.seller_profile_id,
        action=(
            "profile_cr_approve_with_edits" if has_edits
            else "profile_cr_approve"
        ),
        before_json={
            "cr_id": str(cr.id),
            "group": cr.group.value,
            "baseline": cr.baseline_json,
        },
        after_json=audit_after,
        reason=note,
    )
    logger.info(
        "cr.approve cr_id=%s edits=%s group=%s", cr.id, has_edits, cr.group.value,
    )
    from app.services.seller_emails import (
        dispatch_seller_change_request_approved,
    )
    return CRMutationResult(
        cr=cr,
        emails=[lambda: dispatch_seller_change_request_approved(cr.id)],
    )


async def supersede_open_cr(
    *,
    session: AsyncSession,
    seller_profile_id: int,
    group: SellerProfileChangeGroup,
    admin_user_id: int,
    action_name: str,
) -> Optional[SellerProfileChangeRequest]:
    """Mark any open CR for (seller, group) as system-withdrawn.

    Called when an admin uses a direct-override endpoint and bypasses CR.
    Avoids stale baselines. No-op if no open CR exists.
    """
    cr = await _open_cr_for_group(session, seller_profile_id, group)
    if cr is None:
        return None
    cr.status = SellerProfileChangeStatus.Withdrawn
    cr.decided_at = _now()
    cr.decided_by_user_id = admin_user_id
    cr.updated_at = _now()
    session.add(cr)
    _emit_event(
        session=session, cr=cr,
        kind=SellerProfileChangeEventKind.Withdrawn,
        actor_user_id=admin_user_id, actor_role=UserRole.Admin,
        payload_json={
            "reason": "superseded_by_admin_direct_edit",
            "action": action_name,
        },
    )
    logger.info(
        "cr.supersede cr_id=%s seller=%s group=%s action=%s",
        cr.id, seller_profile_id, group.value, action_name,
    )
    return cr
