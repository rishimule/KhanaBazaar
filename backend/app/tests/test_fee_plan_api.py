# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_seller
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeModel,
    FeePayment,
    FeePaymentStatus,
    ServiceFeeConfig,
    ServiceSubscriptionPlan,
)


async def _enrolled(session, bundle):
    session.add(ServiceFeeConfig(service_id=bundle.service_id, subscription_enabled=True))
    session.add(ServiceSubscriptionPlan(service_id=bundle.service_id, duration_months=3, price=300.0, is_active=True))
    session.add(FeeArrangement(
        store_id=bundle.store.id, service_id=bundle.service_id,
        model=FeeModel.Freebie, status=ArrangementStatus.Trial,
        valid_until=None,
    ))
    await session.commit()


@pytest.mark.asyncio
async def test_get_plan_lists_service(client: AsyncClient, session: AsyncSession, approved_seller_with_store) -> None:
    await _enrolled(session, approved_seller_with_store)
    app.dependency_overrides[get_current_seller] = lambda: approved_seller_with_store.user
    try:
        r = await client.get("/api/v1/sellers/me/plan")
        assert r.status_code == 200
        body = r.json()
        svc = next(s for s in body["services"] if s["service_id"] == approved_seller_with_store.service_id)
        assert svc["subscription_enabled"] is True
        assert any(p["duration_months"] == 3 for p in svc["subscription_plans"])
    finally:
        app.dependency_overrides.pop(get_current_seller, None)


@pytest.mark.asyncio
async def test_opt_in_then_mark_paid(client: AsyncClient, session: AsyncSession, approved_seller_with_store) -> None:
    await _enrolled(session, approved_seller_with_store)
    sid = approved_seller_with_store.service_id
    app.dependency_overrides[get_current_seller] = lambda: approved_seller_with_store.user
    try:
        r = await client.post(f"/api/v1/sellers/me/plan/{sid}/opt-in", json={"duration_months": 3})
        assert r.status_code == 200
        r2 = await client.post(f"/api/v1/sellers/me/plan/{sid}/mark-paid", json={"seller_note": "UPI ref 123"})
        assert r2.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
    pay = (await session.exec(select(FeePayment))).first()
    assert pay is not None
    assert pay.status == FeePaymentStatus.Pending
    assert pay.seller_note == "UPI ref 123"


@pytest.mark.asyncio
async def test_opt_in_bad_duration_400(client: AsyncClient, session: AsyncSession, approved_seller_with_store) -> None:
    await _enrolled(session, approved_seller_with_store)
    sid = approved_seller_with_store.service_id
    app.dependency_overrides[get_current_seller] = lambda: approved_seller_with_store.user
    try:
        r = await client.post(f"/api/v1/sellers/me/plan/{sid}/opt-in", json={"duration_months": 4})
        assert r.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
