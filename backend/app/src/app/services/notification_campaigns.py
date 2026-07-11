# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Bulk-notification campaign audience resolution + send orchestration."""
from datetime import date, timedelta
from typing import Any

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.commerce import Order
from app.models.notification_campaign import NotificationAudience, NotificationCampaign
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeModel,
    PlatformFeeSettings,
)
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory

_DEFAULT_EXPIRY_REMINDER_DAYS = 7


async def _customer_ids(session: AsyncSession, f: dict[str, Any]) -> list[int]:
    stmt = select(CustomerProfile.id).distinct()
    state, cities = f.get("state"), f.get("cities")
    if state or cities:
        stmt = stmt.join(
            CustomerAddress,
            CustomerAddress.customer_profile_id == CustomerProfile.id,  # type: ignore[arg-type]
        ).join(Address, Address.id == CustomerAddress.address_id)  # type: ignore[arg-type]
        if state:
            stmt = stmt.where(Address.state == state)
        if cities:
            stmt = stmt.where(func.lower(Address.city).in_([c.lower() for c in cities]))
    if f.get("new_onboarded"):
        ordered = select(Order.customer_profile_id).distinct()
        stmt = stmt.where(col(CustomerProfile.id).not_in(ordered))
    return [int(x) for x in (await session.exec(stmt)).all()]


async def _seller_ids(session: AsyncSession, f: dict[str, Any]) -> list[int]:
    stmt = (
        select(SellerProfile.id)
        .distinct()
        .where(SellerProfile.verification_status == VerificationStatus.Approved)
    )
    state, cities = f.get("state"), f.get("cities")
    if state or cities:
        stmt = stmt.join(
            Address, Address.id == SellerProfile.business_address_id  # type: ignore[arg-type]
        )
        if state:
            stmt = stmt.where(Address.state == state)
        if cities:
            stmt = stmt.where(func.lower(Address.city).in_([c.lower() for c in cities]))

    models = f.get("seller_fee_models")
    expiring = f.get("seller_expiring_soon")
    if models or expiring:
        stmt = stmt.join(
            Store, Store.seller_profile_id == SellerProfile.id  # type: ignore[arg-type]
        ).join(FeeArrangement, FeeArrangement.store_id == Store.id)  # type: ignore[arg-type]
        if models:
            stmt = stmt.where(
                col(FeeArrangement.model).in_([FeeModel(m) for m in models])
            )
        if expiring:
            row = (await session.exec(select(PlatformFeeSettings))).first()
            days = row.expiry_reminder_start_days if row else _DEFAULT_EXPIRY_REMINDER_DAYS
            cutoff = date.today() + timedelta(days=days)
            stmt = stmt.where(
                (FeeArrangement.status == ArrangementStatus.Grace)
                | (
                    col(FeeArrangement.valid_until).is_not(None)
                    & (FeeArrangement.valid_until <= cutoff)
                )
            )
    if f.get("new_onboarded"):
        with_inventory = (
            select(Store.seller_profile_id)
            .join(StoreInventory, StoreInventory.store_id == Store.id)  # type: ignore[arg-type]
            .distinct()
        )
        stmt = stmt.where(col(SellerProfile.id).not_in(with_inventory))
    return [int(x) for x in (await session.exec(stmt)).all()]


async def resolve_recipient_ids(
    session: AsyncSession, campaign: NotificationCampaign
) -> tuple[list[int], list[int]]:
    """Return (customer_profile_ids, seller_profile_ids) for a campaign.

    `Both` ignores all filters (broadcast). De-duplicated within each role.
    """
    audience = campaign.audience
    filters = campaign.filters if audience != NotificationAudience.Both else {}
    customers = (
        await _customer_ids(session, filters)
        if audience in (NotificationAudience.Customers, NotificationAudience.Both)
        else []
    )
    sellers = (
        await _seller_ids(session, filters)
        if audience in (NotificationAudience.Sellers, NotificationAudience.Both)
        else []
    )
    return customers, sellers


async def count_recipients(
    session: AsyncSession, campaign: NotificationCampaign
) -> tuple[int, int]:
    """(customers, sellers) recipient counts — same resolution as the send."""
    customers, sellers = await resolve_recipient_ids(session, campaign)
    return len(customers), len(sellers)
