# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Premium-status derivation + hold-aware reports-gate predicate.

Premium = a store has any non-Freebie arrangement that is live (Active/Grace).
Reports are gated (downgraded) only when a store is not premium AND has an
offerable paid model — so a store with nothing to buy is never stranded.
Stateless reads; no writes, no commit."""
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeModel,
    ServiceFeeConfig,
)
from app.models.profile import SellerProfile, SellerProfileService
from app.models.store import Store

_LIVE_PAID = (ArrangementStatus.Active, ArrangementStatus.Grace)


async def premium_store_ids(
    session: AsyncSession, store_ids: list[int]
) -> set[int]:
    """Subset of store_ids that are premium (≥1 non-Freebie Active/Grace arrangement)."""
    if not store_ids:
        return set()
    rows = (
        await session.exec(
            select(FeeArrangement.store_id).where(
                FeeArrangement.store_id.in_(store_ids),  # type: ignore[attr-defined]
                FeeArrangement.model != FeeModel.Freebie,
                FeeArrangement.status.in_(_LIVE_PAID),  # type: ignore[attr-defined]
            )
        )
    ).all()
    return {int(sid) for sid in rows}


async def is_store_premium(session: AsyncSession, store_id: int) -> bool:
    return bool(await premium_store_ids(session, [store_id]))


async def store_has_offerable_paid_model(
    session: AsyncSession, store_id: int
) -> bool:
    """True if the store's seller offers a service for which the admin has
    enabled any paid model (something the seller could actually opt into)."""
    row = (
        await session.exec(
            select(ServiceFeeConfig.service_id)
            .join(
                SellerProfileService,
                SellerProfileService.service_id == ServiceFeeConfig.service_id,  # type: ignore[arg-type]
            )
            .join(
                SellerProfile,
                SellerProfile.id == SellerProfileService.seller_profile_id,  # type: ignore[arg-type]
            )
            .join(Store, Store.seller_profile_id == SellerProfile.id)  # type: ignore[arg-type]
            .where(
                Store.id == store_id,
                (ServiceFeeConfig.subscription_enabled == True)  # noqa: E712
                | (ServiceFeeConfig.order_value_enabled == True)  # noqa: E712
                | (ServiceFeeConfig.pay_per_txn_enabled == True),  # noqa: E712
            )
            .limit(1)
        )
    ).first()
    return row is not None


async def should_gate_reports(session: AsyncSession, store_id: int) -> bool:
    """Gate (hide) advanced reports only when NOT premium AND a paid model is
    offerable — never strand a store that has nothing to upgrade to."""
    if await is_store_premium(session, store_id):
        return False
    return await store_has_offerable_paid_model(session, store_id)
