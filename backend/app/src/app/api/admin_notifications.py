# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin bulk-notification campaign API (compose, preview, send, image)."""
import anyio
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.base import User
from app.models.notification_campaign import CampaignStatus, NotificationCampaign
from app.schemas.notification_campaigns import (
    AudienceCount,
    CampaignCreate,
    CampaignRead,
    CampaignUpdate,
)
from app.services.image_processing import ImageValidationError, process_image
from app.services.image_storage import get_image_storage
from app.services.notification_campaigns import count_recipients

admin_router = APIRouter()


async def _get_campaign(session: AsyncSession, cid: int) -> NotificationCampaign:
    campaign = await session.get(NotificationCampaign, cid)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign_not_found")
    return campaign


def _require_draft(campaign: NotificationCampaign) -> None:
    if campaign.status != CampaignStatus.Draft:
        raise HTTPException(status_code=409, detail="campaign_not_draft")


@admin_router.post(
    "/notifications/campaigns",
    response_model=CampaignRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_campaign(
    body: CampaignCreate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> CampaignRead:
    assert admin.id is not None
    campaign = NotificationCampaign(
        audience=body.audience,
        filters=body.filters,
        channels=body.channels,
        title=body.title,
        body=body.body,
        cta_url=body.cta_url,
        cta_label=body.cta_label,
        is_essential=body.is_essential,
        status=CampaignStatus.Draft,
        created_by_admin_id=admin.id,
    )
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)
    return CampaignRead.model_validate(campaign)


@admin_router.get("/notifications/campaigns", response_model=list[CampaignRead])
async def list_campaigns(
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> list[CampaignRead]:
    rows = (
        await session.exec(
            select(NotificationCampaign).order_by(
                col(NotificationCampaign.created_at).desc()
            )
        )
    ).all()
    return [CampaignRead.model_validate(r) for r in rows]


@admin_router.get("/notifications/campaigns/{cid}", response_model=CampaignRead)
async def get_campaign(
    cid: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> CampaignRead:
    return CampaignRead.model_validate(await _get_campaign(session, cid))


@admin_router.patch("/notifications/campaigns/{cid}", response_model=CampaignRead)
async def update_campaign(
    cid: int,
    body: CampaignUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> CampaignRead:
    campaign = await _get_campaign(session, cid)
    _require_draft(campaign)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(campaign, field, value)
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)
    return CampaignRead.model_validate(campaign)


@admin_router.post(
    "/notifications/campaigns/{cid}/audience-count", response_model=AudienceCount
)
async def campaign_audience_count(
    cid: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> AudienceCount:
    campaign = await _get_campaign(session, cid)
    customers, sellers = await count_recipients(session, campaign)
    return AudienceCount(customers=customers, sellers=sellers)


@admin_router.post("/notifications/campaigns/{cid}/send", response_model=CampaignRead)
async def send_campaign_endpoint(
    cid: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> CampaignRead:
    campaign = await _get_campaign(session, cid)
    _require_draft(campaign)
    from app.worker import send_campaign_async

    send_campaign_async.delay(cid)
    await session.refresh(campaign)  # eager mode has already flipped it to sent
    return CampaignRead.model_validate(campaign)


@admin_router.post("/notifications/campaigns/{cid}/image", response_model=CampaignRead)
async def upload_campaign_image(
    cid: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> CampaignRead:
    campaign = await _get_campaign(session, cid)
    _require_draft(campaign)
    raw = await file.read()
    try:
        data, digest = await anyio.to_thread.run_sync(process_image, raw)
    except ImageValidationError as exc:
        code = str(exc)
        http_status = 413 if code == "file_too_large" else 422
        raise HTTPException(status_code=http_status, detail=code) from exc
    key = f"campaigns/{digest}.webp"
    url = await get_image_storage().save(key, data, "image/webp")
    campaign.image_url = url
    campaign.image_storage_key = key
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)
    return CampaignRead.model_validate(campaign)
