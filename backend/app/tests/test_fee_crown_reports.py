# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform_fee import ArrangementStatus, FeeArrangement, FeeModel


async def _paid_active(session, store_id, service_id):
    session.add(FeeArrangement(
        store_id=store_id, service_id=service_id, model=FeeModel.Subscription,
        status=ArrangementStatus.Active, valid_until=date(2026, 12, 1),
    ))
    await session.commit()


@pytest.mark.asyncio
async def test_store_detail_crown_true_when_paid(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store
) -> None:
    await _paid_active(session, approved_seller_with_store.store.id, approved_seller_with_store.service_id)
    r = await client.get(f"/api/v1/stores/{approved_seller_with_store.store.id}")
    assert r.status_code == 200
    assert r.json()["is_premium"] is True


@pytest.mark.asyncio
async def test_store_detail_crown_false_when_freebie(
    client: AsyncClient, approved_seller_with_store
) -> None:
    r = await client.get(f"/api/v1/stores/{approved_seller_with_store.store.id}")
    assert r.status_code == 200
    assert r.json()["is_premium"] is False


@pytest.mark.asyncio
async def test_store_list_marks_premium(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store
) -> None:
    await _paid_active(session, approved_seller_with_store.store.id, approved_seller_with_store.service_id)
    r = await client.get("/api/v1/stores/")
    assert r.status_code == 200
    row = next(s for s in r.json() if s["id"] == approved_seller_with_store.store.id)
    assert row["is_premium"] is True
