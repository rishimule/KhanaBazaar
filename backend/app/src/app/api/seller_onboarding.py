# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.otp import InvalidPhoneNumber, normalize_email, normalize_phone
from app.core.rate_limit import incr_with_ttl
from app.core.redis import get_redis
from app.core.security import get_optional_current_user
from app.db.session import get_db_session
from app.models.base import User
from app.models.seller_onboarding_request import SellerOnboardingRequest
from app.schemas.seller_onboarding import (
    SellerOnboardingRequestCreate,
    SellerOnboardingRequestRead,
)

router = APIRouter()

ONBOARDING_REQUEST_RATE_LIMIT_PER_HOUR = 5


@router.post(
    "",
    response_model=SellerOnboardingRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_seller_onboarding_request(
    body: SellerOnboardingRequestCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    current_user: User | None = Depends(get_optional_current_user),
) -> SellerOnboardingRequest:
    """Public lead capture: a visitor suggests a seller/store to onboard.

    Works before and after login. Rate-limited per client IP. Best-effort
    admin notification email; never blocks the insert.
    """
    ip = request.client.host if request.client else "unknown"
    count = await incr_with_ttl(redis, f"onboarding_request:hourly:{ip}", 3600)
    if count > ONBOARDING_REQUEST_RATE_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429, detail={"error": "rate_limited"})

    try:
        phone = normalize_phone(body.contact_phone)
    except InvalidPhoneNumber as exc:
        raise HTTPException(
            status_code=422, detail={"error": "phone_invalid"}
        ) from exc

    row = SellerOnboardingRequest(
        store_name=body.store_name.strip(),
        contact_phone=phone,
        contact_email=normalize_email(body.contact_email),
        contact_address=body.contact_address.strip(),
        preferred_categories=(body.preferred_categories or None),
        area_lat=body.area_lat,
        area_lng=body.area_lng,
        area_label=body.area_label,
        source=body.source,
        submitted_by_user_id=current_user.id if current_user else None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    # Best-effort admin notification; never block the insert.
    try:
        from app.worker import send_seller_onboarding_request_email

        send_seller_onboarding_request_email.delay(
            row.store_name,
            row.contact_phone,
            row.contact_email,
            row.contact_address,
            row.preferred_categories,
            row.area_label,
            row.source,
        )
    except Exception:  # noqa: BLE001 - notification is non-critical
        pass

    return row
