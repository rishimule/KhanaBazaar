# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Return-order endpoints for customers, sellers, and admins.

Four routers, mounted at four prefixes (mirrors `platform_fees.py`):
  * ``router``              → /returns        (customer)
  * ``store_credit_router`` → /store-credit   (customer; a balance outlives the
                                               return that created it)
  * ``seller_router``       → /sellers
  * ``admin_router``        → /admin
"""
import logging

from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_customer
from app.db.session import get_db_session
from app.models.base import User
from app.models.commerce import Order
from app.models.consent import PolicyKind
from app.models.profile import CustomerProfile
from app.schemas.returns import ReturnEligibilityLine, ReturnEligibilityRead
from app.services import returns as returns_svc
from app.services.consent import get_current_version

router = APIRouter()
store_credit_router = APIRouter()
seller_router = APIRouter()
admin_router = APIRouter()

logger = logging.getLogger(__name__)


async def _customer_profile_id(session: AsyncSession, user: User) -> int:
    profile_id = (
        await session.exec(
            select(CustomerProfile.id).where(CustomerProfile.user_id == user.id)
        )
    ).first()
    if profile_id is None:
        raise returns_svc.ReturnError(404, "customer_profile_not_found")
    return int(profile_id)


async def _owned_order(session: AsyncSession, order_id: int, profile_id: int) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise returns_svc.ReturnError(404, "order_not_found")
    if order.customer_profile_id != profile_id:
        raise returns_svc.ReturnError(403, "forbidden")
    return order


@router.get("/eligibility/{order_id}", response_model=ReturnEligibilityRead)
async def return_eligibility(
    order_id: int,
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnEligibilityRead:
    profile_id = await _customer_profile_id(session, user)
    order = await _owned_order(session, order_id, profile_id)
    result = await returns_svc.compute_eligibility(
        session, order=order, customer_profile_id=profile_id
    )
    agreement_version = await get_current_version(session, PolicyKind.return_agreement)
    return ReturnEligibilityRead(
        order_id=order_id,
        eligible=result.eligible,
        reason_code=result.reason_code,
        window_expires_at=result.window_expires_at,
        delivery_fee=result.delivery_fee,
        full_order_available=result.full_order_available,
        agreement_version=agreement_version or None,
        lines=[
            ReturnEligibilityLine(
                order_item_id=line.order_item_id, product_name=line.product_name,
                unit_price=line.unit_price, quantity=line.quantity,
                line_total=line.line_total, returnable=line.returnable,
                lock_reason=line.lock_reason,
            )
            for line in result.lines
        ],
    )
