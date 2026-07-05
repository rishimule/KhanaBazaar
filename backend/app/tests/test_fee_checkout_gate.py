# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date

import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform_fee import ArrangementStatus, FeeArrangement, FeeModel
from app.services.checkout import _validate_service_active_for_store


@pytest.mark.asyncio
async def test_suspended_service_blocks_checkout(
    session: AsyncSession, approved_seller_with_store
) -> None:
    store = approved_seller_with_store.store
    sid = approved_seller_with_store.service_id
    session.add(FeeArrangement(
        store_id=store.id, service_id=sid, model=FeeModel.Freebie,
        status=ArrangementStatus.Suspended, valid_until=date(2026, 7, 1),
    ))
    await session.commit()
    with pytest.raises(HTTPException) as exc:
        await _validate_service_active_for_store(session, store.id, sid)
    assert exc.value.status_code == 409
    assert exc.value.detail["detail"] == "service_suspended"


@pytest.mark.asyncio
async def test_trial_service_passes_checkout(
    session: AsyncSession, approved_seller_with_store
) -> None:
    store = approved_seller_with_store.store
    sid = approved_seller_with_store.service_id
    session.add(FeeArrangement(
        store_id=store.id, service_id=sid, model=FeeModel.Freebie,
        status=ArrangementStatus.Trial, valid_until=date(2026, 12, 1),
    ))
    await session.commit()
    # Should not raise (service offered, active, not paused, not suspended).
    await _validate_service_active_for_store(session, store.id, sid)
