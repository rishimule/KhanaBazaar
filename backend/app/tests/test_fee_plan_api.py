# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_seller
from app.models.base import User, UserRole
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeModel,
    FeePayment,
    FeePaymentStatus,
    ServiceFeeConfig,
    ServiceSubscriptionPlan,
)


async def _persist_test_admin(session: AsyncSession) -> None:
    """`admin_auth_headers` only overrides the auth dependency in-process; the
    admin id it uses (99001) must also exist as a real row for FK columns like
    `FeePayment.confirmed_by_admin_id` to insert successfully."""
    existing = await session.get(User, 99001)
    if existing is None:
        session.add(User(id=99001, email="admin-test@kb.com", role=UserRole.Admin, is_active=True))
        await session.commit()


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
async def test_me_plan_nulls_disabled_method_fields(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store
) -> None:
    from app.services.platform_fees import get_or_create_settings

    await _enrolled(session, approved_seller_with_store)
    settings = await get_or_create_settings(session)
    settings.upi_id = "pay@oksbi"
    settings.qr_image_url = "http://x/q.png"
    settings.bank_account_number = "123456"
    settings.bank_ifsc = "HDFC0001"
    settings.upi_enabled = False  # disabled → its details must be withheld
    settings.bank_transfer_enabled = True
    session.add(settings)
    await session.commit()

    app.dependency_overrides[get_current_seller] = lambda: approved_seller_with_store.user
    try:
        r = await client.get("/api/v1/sellers/me/plan")
        assert r.status_code == 200
        pd = r.json()["payment_details"]
        assert pd["upi_enabled"] is False and pd["bank_transfer_enabled"] is True
        # Disabled UPI → fields nulled; enabled bank → fields present.
        assert pd["upi_id"] is None and pd["qr_image_url"] is None
        assert pd["bank_account_number"] == "123456"
        assert pd["bank_ifsc"] == "HDFC0001"
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


@pytest.mark.asyncio
async def test_admin_queue_confirm_activates(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store, admin_auth_headers
) -> None:
    await _persist_test_admin(session)
    await _enrolled(session, approved_seller_with_store)
    sid = approved_seller_with_store.service_id
    app.dependency_overrides[get_current_seller] = lambda: approved_seller_with_store.user
    try:
        await client.post(f"/api/v1/sellers/me/plan/{sid}/opt-in", json={"duration_months": 3})
    finally:
        app.dependency_overrides.pop(get_current_seller, None)

    q = await client.get("/api/v1/admin/fees/queue", headers=admin_auth_headers)
    assert q.status_code == 200
    item = next(i for i in q.json() if i["service_id"] == sid)
    r = await client.post(
        f"/api/v1/admin/fees/payments/{item['payment_id']}/confirm", headers=admin_auth_headers
    )
    assert r.status_code == 200
    arr = (await session.exec(
        select(FeeArrangement).where(FeeArrangement.service_id == sid)
    )).first()
    assert arr.status == ArrangementStatus.Active
    assert arr.model == FeeModel.Subscription


@pytest.mark.asyncio
async def test_admin_reject_leaves_arrangement(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store, admin_auth_headers
) -> None:
    await _persist_test_admin(session)
    await _enrolled(session, approved_seller_with_store)
    sid = approved_seller_with_store.service_id
    app.dependency_overrides[get_current_seller] = lambda: approved_seller_with_store.user
    try:
        await client.post(f"/api/v1/sellers/me/plan/{sid}/opt-in", json={"duration_months": 3})
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
    q = await client.get("/api/v1/admin/fees/queue", headers=admin_auth_headers)
    pid = next(i for i in q.json() if i["service_id"] == sid)["payment_id"]
    r = await client.post(
        f"/api/v1/admin/fees/payments/{pid}/reject",
        headers=admin_auth_headers, json={"reason": "not received"},
    )
    assert r.status_code == 200
    arr = (await session.exec(select(FeeArrangement).where(FeeArrangement.service_id == sid))).first()
    assert arr.status == ArrangementStatus.Trial  # unchanged
    assert arr.pending_since is None
