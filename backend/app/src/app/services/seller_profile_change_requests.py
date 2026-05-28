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

from app.models.base import UserRole
from app.models.profile import (
    SellerProfile,
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
from app.schemas.seller_profile_change_request import (
    validate_group_payload,
)
from app.services.profiles import compose_full_name
from app.services.seller_services import (
    list_profile_services,
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
