# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Both notification feeds carry the return id, so the bells can deep-link."""
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import NotificationType
from app.models.returns import (
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnSettlementChoice,
    ReturnStatus,
)
from app.services.notifications import record_return_notification
from tests._returns_helpers import (
    as_customer,
    as_seller,
    clear_overrides,
    pk,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def test_both_feeds_expose_the_return_id(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.seller,
        initiated_by_user_id=seed.seller_user_id,
        status=ReturnStatus.awaiting_customer_confirmation, is_full_order=False,
        reason_code=ReturnReasonCode.damaged, items_amount=10.0,
        delivery_fee_amount=0.0, total_amount=10.0,
        settlement_choice=ReturnSettlementChoice.store_credit,
        agreement_policy_version=1, window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48),
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    rid = pk(req.id)
    await record_return_notification(
        session, return_request_id=rid, type=NotificationType.ReturnStatusUpdate,
        title="t", body="b", status_value="awaiting_customer_confirmation",
        customer_profile_id=seed.customer_profile_id,
    )
    await record_return_notification(
        session, return_request_id=rid, type=NotificationType.SellerReturnRequest,
        title="t", body="b", status_value="awaiting_customer_confirmation",
        seller_profile_id=seed.seller_profile_id,
    )
    await session.commit()

    as_customer(seed.customer_user)
    customer_feed = (await client.get("/api/v1/notifications")).json()
    clear_overrides()
    as_seller(seed.seller_user)
    seller_feed = (await client.get("/api/v1/sellers/me/notifications")).json()

    assert [n["return_request_id"] for n in customer_feed["notifications"]] == [rid]
    assert [n["return_request_id"] for n in seller_feed["notifications"]] == [rid]
