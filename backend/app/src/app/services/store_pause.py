# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pause/unpause a store or one of its services.

Pause is an independent, reversible lever distinct from the admin-only
``Store.is_active`` hard switch. Mutations here only stage the change and add an
audit row when an admin acts — the caller owns the commit so the audit row lands
in the same transaction (see services.admin_audit)."""
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.admin_audit import AdminActionTargetType
from app.models.profile import SellerProfileService
from app.models.store import Store
from app.services import admin_audit


async def set_store_pause(
    session: AsyncSession,
    store: Store,
    *,
    is_paused: bool,
    reason: Optional[str],
    paused_until: Optional[date],
    acting_admin_id: Optional[int] = None,
) -> Store:
    before = {
        "is_paused": store.is_paused,
        "pause_reason": store.pause_reason,
        "paused_until": store.paused_until.isoformat() if store.paused_until else None,
    }
    store.is_paused = is_paused
    store.pause_reason = reason if is_paused else None
    store.paused_until = paused_until if is_paused else None
    session.add(store)
    if acting_admin_id is not None:
        assert store.id is not None
        await admin_audit.log(
            session=session,
            admin_user_id=acting_admin_id,
            target_seller_id=store.seller_profile_id,
            target_type=AdminActionTargetType.Store,
            target_id=store.id,
            action="store.set_pause",
            before_json=before,
            after_json={
                "is_paused": store.is_paused,
                "pause_reason": store.pause_reason,
                "paused_until": store.paused_until.isoformat() if store.paused_until else None,
            },
        )
    return store


async def set_service_pause(
    session: AsyncSession,
    *,
    seller_profile_id: int,
    service_id: int,
    is_paused: bool,
    reason: Optional[str],
    paused_until: Optional[date],
    acting_admin_id: Optional[int] = None,
) -> SellerProfileService:
    row = (
        await session.exec(
            select(SellerProfileService).where(
                SellerProfileService.seller_profile_id == seller_profile_id,
                SellerProfileService.service_id == service_id,
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Service not offered by this seller")
    before = {
        "service_id": service_id,
        "is_paused": row.is_paused,
        "pause_reason": row.pause_reason,
        "paused_until": row.paused_until.isoformat() if row.paused_until else None,
    }
    row.is_paused = is_paused
    row.pause_reason = reason if is_paused else None
    row.paused_until = paused_until if is_paused else None
    session.add(row)
    if acting_admin_id is not None:
        await admin_audit.log(
            session=session,
            admin_user_id=acting_admin_id,
            target_seller_id=seller_profile_id,
            target_type=AdminActionTargetType.SellerProfile,
            target_id=seller_profile_id,
            action="service.set_pause",
            before_json=before,
            after_json={
                "service_id": service_id,
                "is_paused": row.is_paused,
                "pause_reason": row.pause_reason,
                "paused_until": row.paused_until.isoformat() if row.paused_until else None,
            },
        )
    return row
