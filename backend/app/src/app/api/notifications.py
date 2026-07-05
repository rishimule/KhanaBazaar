# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_customer, get_current_seller
from app.db.session import get_db_session
from app.models.base import User
from app.models.profile import CustomerProfile, SellerProfile
from app.schemas.notifications import (
    NotificationListResponse,
    NotificationRead,
    PushSubscribeRequest,
    PushUnsubscribeRequest,
)
from app.services.notifications import (
    delete_push_subscription,
    list_notifications,
    mark_all_read,
    mark_notification_read,
    upsert_push_subscription,
)

router = APIRouter()


async def _customer_profile_id(session: AsyncSession, user: User) -> int:
    result = await session.exec(
        select(CustomerProfile.id).where(CustomerProfile.user_id == user.id)
    )
    profile_id = result.first()
    if profile_id is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return profile_id


@router.get("", response_model=NotificationListResponse)
@router.get("/", response_model=NotificationListResponse, include_in_schema=False)
async def get_notifications(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> NotificationListResponse:
    cpid = await _customer_profile_id(session, user)
    items, unread = await list_notifications(session, customer_profile_id=cpid)
    return NotificationListResponse(
        notifications=[
            NotificationRead(
                id=n.id if n.id is not None else 0,
                order_id=n.order_id,
                type=n.type.value,
                title=n.title,
                body=n.body,
                status_value=n.status_value,
                read=n.read,
                created_at=n.created_at,
            )
            for n in items
        ],
        unread_count=unread,
    )


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_notification(
    notification_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> Response:
    cpid = await _customer_profile_id(session, user)
    ok = await mark_notification_read(
        session, customer_profile_id=cpid, notification_id=notification_id
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all_notifications(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> Response:
    cpid = await _customer_profile_id(session, user)
    await mark_all_read(session, customer_profile_id=cpid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/push/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe_push(
    payload: PushSubscribeRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> Response:
    cpid = await _customer_profile_id(session, user)
    await upsert_push_subscription(
        session,
        customer_profile_id=cpid,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
        user_agent=payload.user_agent,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/push/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe_push(
    payload: PushUnsubscribeRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> Response:
    cpid = await _customer_profile_id(session, user)
    await delete_push_subscription(
        session, customer_profile_id=cpid, endpoint=payload.endpoint
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


seller_router = APIRouter()


async def _seller_profile_id(session: AsyncSession, user: User) -> int:
    result = await session.exec(
        select(SellerProfile.id).where(SellerProfile.user_id == user.id)
    )
    spid = result.first()
    if spid is None:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    return spid


@seller_router.get("/me/notifications", response_model=NotificationListResponse)
async def get_seller_notifications(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_seller),
) -> NotificationListResponse:
    spid = await _seller_profile_id(session, user)
    items, unread = await list_notifications(session, seller_profile_id=spid)
    return NotificationListResponse(
        notifications=[
            NotificationRead(
                id=n.id if n.id is not None else 0,
                order_id=n.order_id,
                type=n.type.value,
                title=n.title,
                body=n.body,
                status_value=n.status_value,
                read=n.read,
                created_at=n.created_at,
            )
            for n in items
        ],
        unread_count=unread,
    )


@seller_router.post("/me/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_seller_notification(
    notification_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_seller),
) -> Response:
    spid = await _seller_profile_id(session, user)
    ok = await mark_notification_read(
        session, seller_profile_id=spid, notification_id=notification_id
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@seller_router.post("/me/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all_seller_notifications(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_seller),
) -> Response:
    spid = await _seller_profile_id(session, user)
    await mark_all_read(session, seller_profile_id=spid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
