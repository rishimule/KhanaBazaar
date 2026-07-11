# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Bulk-notification campaign audience resolution + send orchestration."""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator

from fastapi import HTTPException
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User
from app.models.commerce import Order
from app.models.notification_campaign import (
    CampaignStatus,
    NotificationAudience,
    NotificationCampaign,
)
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
from app.services.notification_push import dispatch_notification_push
from app.services.notifications import record_campaign_notification

logger = logging.getLogger(__name__)

_DEFAULT_EXPIRY_REMINDER_DAYS = 7
_BATCH = 200


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


def _chunks(items: list[int], size: int) -> Iterator[list[int]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _enqueue_email(campaign_id: int, to_email: str) -> None:
    from app.worker import send_campaign_email_async

    send_campaign_email_async.delay(campaign_id, to_email)


def _enqueue_sms(campaign_id: int, to_phone: str) -> None:
    from app.worker import send_campaign_sms_async

    send_campaign_sms_async.delay(campaign_id, to_phone)


async def send_campaign(session: AsyncSession, campaign_id: int) -> None:
    """Fan a draft campaign out to its resolved audience.

    Writes one in-app Notification per recipient (best-effort Web Push for
    customers), enqueues per-recipient Email/SMS for the selected channels
    honoring `marketing_opt_in` (bypassed when `is_essential`), updates the
    aggregate counts, and flips the campaign Draft→Sending→Sent. Any unexpected
    error sets status=Failed and re-raises. Individual channel failures are
    best-effort and never abort the campaign.
    """
    campaign = await session.get(NotificationCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign_not_found")
    if campaign.status != CampaignStatus.Draft:
        raise HTTPException(status_code=409, detail="campaign_not_draft")

    campaign.status = CampaignStatus.Sending
    await session.commit()

    try:
        cust_ids, sell_ids = await resolve_recipient_ids(session, campaign)
        campaign.recipients_targeted = len(cust_ids) + len(sell_ids)
        want_email = "email" in campaign.channels
        want_sms = "sms" in campaign.channels
        inapp = email_n = sms_n = 0

        def _content() -> dict[str, Any]:
            return {
                "campaign_id": campaign.id,
                "title": campaign.title,
                "body": campaign.body,
                "image_url": campaign.image_url,
                "cta_url": campaign.cta_url,
                "cta_label": campaign.cta_label,
            }

        # Customers: in-app (+push), external gated on opt-in unless essential.
        for batch in _chunks(cust_ids, _BATCH):
            rows = (
                await session.exec(
                    select(CustomerProfile, User.email)
                    .join(User, User.id == CustomerProfile.user_id)  # type: ignore[arg-type]
                    .where(col(CustomerProfile.id).in_(batch))
                )
            ).all()
            for prof, email in rows:
                notif = await record_campaign_notification(
                    session, **_content(), customer_profile_id=prof.id
                )
                inapp += 1
                if notif.id is not None:
                    dispatch_notification_push(notif.id)
                external_ok = prof.marketing_opt_in or campaign.is_essential
                if external_ok and want_email and email:
                    _enqueue_email(campaign.id, email)
                    email_n += 1
                if external_ok and want_sms and prof.phone:
                    _enqueue_sms(campaign.id, prof.phone)
                    sms_n += 1
            await session.commit()

        # Sellers: in-app + external always (operational comms). No push.
        for batch in _chunks(sell_ids, _BATCH):
            rows = (
                await session.exec(
                    select(SellerProfile, User.email)
                    .join(User, User.id == SellerProfile.user_id)  # type: ignore[arg-type]
                    .where(col(SellerProfile.id).in_(batch))
                )
            ).all()
            for prof, email in rows:
                await record_campaign_notification(
                    session, **_content(), seller_profile_id=prof.id
                )
                inapp += 1
                if want_email and email:
                    _enqueue_email(campaign.id, email)
                    email_n += 1
                if want_sms and prof.phone:
                    _enqueue_sms(campaign.id, prof.phone)
                    sms_n += 1
            await session.commit()

        campaign.inapp_created = inapp
        campaign.email_enqueued = email_n
        campaign.sms_enqueued = sms_n
        campaign.status = CampaignStatus.Sent
        campaign.sent_at = datetime.now(timezone.utc)
        await session.commit()
    except HTTPException:
        raise
    except Exception:
        logger.exception("Campaign send failed for campaign_id=%s", campaign_id)
        campaign.status = CampaignStatus.Failed
        await session.commit()
        raise
