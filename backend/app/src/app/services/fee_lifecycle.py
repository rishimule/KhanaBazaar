# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Freebie-phase fee lifecycle: idempotent auto-enrollment of (store, service)
pairs into a Freebie Trial arrangement, and the daily sweep that expires trials
(Trial→Grace→Suspended), holding when no paid model is offerable.

Pure/service-layer logic; callers own the commit. Seller notifications +
expiry reminders are added in Plan 3."""
from datetime import date, timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeEvent,
    FeeEventType,
    FeeModel,
    ServiceFeeConfig,
)
from app.models.profile import SellerProfileService
from app.models.store import Store

DEFAULT_FREEBIE_DAYS = 30
DEFAULT_GRACE_DAYS = 2


async def _freebie_days_by_service(
    session: AsyncSession, service_ids: list[int]
) -> dict[int, int]:
    if not service_ids:
        return {}
    rows = (
        await session.exec(
            select(
                ServiceFeeConfig.service_id, ServiceFeeConfig.freebie_default_days
            ).where(ServiceFeeConfig.service_id.in_(service_ids))  # type: ignore[attr-defined]
        )
    ).all()
    return dict(rows)


async def sync_store_arrangements(
    session: AsyncSession, seller_profile_id: int, *, today: date | None = None
) -> None:
    """Ensure every service the seller currently offers has a Freebie Trial
    arrangement for their store; delete arrangements (and their events) for
    services no longer offered. No-op if the seller has no store yet. Idempotent
    — an existing arrangement is left untouched (its valid_until is preserved).
    Caller commits."""
    today = today or date.today()
    store = (
        await session.exec(
            select(Store).where(Store.seller_profile_id == seller_profile_id)
        )
    ).first()
    if store is None or store.id is None:
        return
    offered = set(
        (
            await session.exec(
                select(SellerProfileService.service_id).where(
                    SellerProfileService.seller_profile_id == seller_profile_id
                )
            )
        ).all()
    )
    existing_rows = (
        await session.exec(
            select(FeeArrangement).where(FeeArrangement.store_id == store.id)
        )
    ).all()
    existing = {r.service_id: r for r in existing_rows}

    to_create = [sid for sid in offered if sid not in existing]
    days_by_service = await _freebie_days_by_service(session, to_create)
    for sid in to_create:
        days = days_by_service.get(sid, DEFAULT_FREEBIE_DAYS)
        arr = FeeArrangement(
            store_id=store.id,
            service_id=sid,
            model=FeeModel.Freebie,
            status=ArrangementStatus.Trial,
            valid_until=today + timedelta(days=days),
        )
        session.add(arr)
        await session.flush()
        session.add(
            FeeEvent(
                arrangement_id=arr.id,
                event_type=FeeEventType.ArrangementCreated,
                actor="system",
                note=f"freebie trial {days}d",
            )
        )

    for sid, row in existing.items():
        if sid not in offered:
            # Freebie arrangement for a dropped service: remove it + its events
            # (no financial history to preserve). A re-add creates a fresh trial.
            events = (
                await session.exec(
                    select(FeeEvent).where(FeeEvent.arrangement_id == row.id)
                )
            ).all()
            for ev in events:
                await session.delete(ev)
            await session.delete(row)
    await session.flush()
