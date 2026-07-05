# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User, UserRole
from app.models.platform_fee import ArrangementStatus, FeeArrangement, FeeModel
from app.services.fee_lifecycle import (
    admin_comp_subscription,
    admin_extend,
    admin_terminate,
)


async def _arr(session, bundle, *, model=FeeModel.Freebie, status=ArrangementStatus.Trial, valid_until=date(2026, 8, 1)):
    arr = FeeArrangement(
        store_id=bundle.store.id, service_id=bundle.service_id,
        model=model, status=status, valid_until=valid_until,
    )
    session.add(arr)
    await session.flush()
    return arr


async def _persist_test_admin(session: AsyncSession) -> None:
    """`admin_auth_headers` only overrides the auth dependency in-process; the
    admin id it uses (99001) must also exist as a real row for FK columns like
    `AdminActionLog.admin_user_id` to insert successfully."""
    existing = await session.get(User, 99001)
    if existing is None:
        session.add(User(id=99001, email="admin-test@kb.com", role=UserRole.Admin, is_active=True))
        await session.commit()


@pytest.mark.asyncio
async def test_admin_extend(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _arr(session, approved_seller_with_store, valid_until=date(2026, 8, 1))
    admin_extend(session, arr, 15, admin_user_id=1)
    await session.flush()
    assert arr.valid_until == date(2026, 8, 16)


@pytest.mark.asyncio
async def test_admin_extend_from_none_uses_today(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _arr(session, approved_seller_with_store, valid_until=None)
    admin_extend(session, arr, 10, admin_user_id=1)
    await session.flush()
    assert arr.valid_until == date.today() + timedelta(days=10)


@pytest.mark.asyncio
async def test_admin_terminate(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _arr(session, approved_seller_with_store, model=FeeModel.Subscription, status=ArrangementStatus.Active)
    admin_terminate(session, arr, "policy violation", admin_user_id=1)
    await session.flush()
    assert arr.status == ArrangementStatus.Suspended
    assert arr.suspended_reason == "policy violation"
    assert arr.auto_renew is False


@pytest.mark.asyncio
async def test_admin_comp_subscription(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _arr(session, approved_seller_with_store, status=ArrangementStatus.Suspended, valid_until=date(2026, 7, 1))
    admin_comp_subscription(session, arr, 6, admin_user_id=1, today=date(2026, 7, 5))
    await session.flush()
    assert arr.model == FeeModel.Subscription
    assert arr.status == ArrangementStatus.Active
    assert arr.subscription_duration_months == 6
    assert arr.price_snapshot == 0.0
    assert arr.valid_until == date(2026, 7, 5) + timedelta(days=180)
    assert arr.suspended_at is None


@pytest.mark.asyncio
async def test_admin_list_arrangements(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store, admin_auth_headers
) -> None:
    await _arr(session, approved_seller_with_store)
    await session.commit()
    r = await client.get(
        f"/api/v1/admin/fees/arrangements/{approved_seller_with_store.store.id}",
        headers=admin_auth_headers,
    )
    assert r.status_code == 200
    assert any(a["service_id"] == approved_seller_with_store.service_id for a in r.json())


@pytest.mark.asyncio
async def test_admin_terminate_endpoint_audits(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store, admin_auth_headers
) -> None:
    await _persist_test_admin(session)
    arr = await _arr(session, approved_seller_with_store, model=FeeModel.Subscription, status=ArrangementStatus.Active)
    await session.commit()
    r = await client.post(
        f"/api/v1/admin/fees/arrangements/{arr.id}/terminate",
        headers=admin_auth_headers, json={"reason": "abuse"},
    )
    assert r.status_code == 200
    refreshed = await session.get(FeeArrangement, arr.id)
    await session.refresh(refreshed)
    assert refreshed.status == ArrangementStatus.Suspended
    # Audit row written.
    from sqlmodel import select

    from app.models.admin_audit import AdminActionLog
    logs = (await session.exec(select(AdminActionLog).where(AdminActionLog.action == "fee.terminate"))).all()
    assert len(logs) >= 1


@pytest.mark.asyncio
async def test_admin_terminate_requires_reason(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store, admin_auth_headers
) -> None:
    await _persist_test_admin(session)
    arr = await _arr(session, approved_seller_with_store)
    await session.commit()
    r = await client.post(
        f"/api/v1/admin/fees/arrangements/{arr.id}/terminate",
        headers=admin_auth_headers, json={},
    )
    assert r.status_code == 422  # reason required


@pytest.mark.asyncio
async def test_admin_comp_endpoint(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store, admin_auth_headers
) -> None:
    await _persist_test_admin(session)
    arr = await _arr(session, approved_seller_with_store, status=ArrangementStatus.Suspended)
    await session.commit()
    r = await client.post(
        f"/api/v1/admin/fees/arrangements/{arr.id}/comp",
        headers=admin_auth_headers, json={"duration_months": 3},
    )
    assert r.status_code == 200
    refreshed = await session.get(FeeArrangement, arr.id)
    await session.refresh(refreshed)
    assert refreshed.model == FeeModel.Subscription
    assert refreshed.status == ArrangementStatus.Active
