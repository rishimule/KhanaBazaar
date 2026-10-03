# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any

import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.profile import SellerProfile, SellerProfileService
from app.models.seller_profile_change_request import (
    SellerProfileChangeGroup,
    SellerProfileChangeRequest,
)
from app.models.store import Store
from app.services.seller_profile_change_requests import approve, create_change_request
from tests._courier_helpers import ADMIN, SELLER, CourierWorld, seed_courier_world

G = SellerProfileChangeGroup
SELLER_ID = int(SELLER.id or 0)
ADMIN_ID = int(ADMIN.id or 0)


async def _create(
    session: AsyncSession, world: CourierWorld, group: G, proposed: dict[str, Any]
) -> SellerProfileChangeRequest:
    profile = await session.get(SellerProfile, world.seller_profile_id)
    assert profile is not None
    result = await create_change_request(
        session=session, seller_profile=profile, group=group,
        proposed=proposed, note=None, actor_user_id=SELLER_ID,
    )
    await session.commit()
    return result.cr


async def _approve(session: AsyncSession, cr: Any, applied: dict[str, Any] | None = None) -> None:
    await approve(session=session, cr=cr, admin_user_id=ADMIN_ID, applied=applied)
    await session.commit()


async def _store(session: AsyncSession, world: CourierWorld) -> Store:
    store = await session.get(Store, world.store_id)
    assert store is not None
    await session.refresh(store)
    return store


async def test_store_basics_sets_and_clears_courier_radius(session: AsyncSession) -> None:
    world = await seed_courier_world(session, courier_radius_km=None)
    cr = await _create(session, world, G.StoreBasics, {"delivery_radius_km": 5, "courier_radius_km": 800})
    assert cr.proposed_json["courier_radius_km"] == 800
    assert cr.baseline_json["courier_radius_km"] is None
    await _approve(session, cr)
    assert (await _store(session, world)).courier_radius_km == 800
    cr2 = await _create(session, world, G.StoreBasics, {"delivery_radius_km": 5, "courier_radius_km": 0})
    await _approve(session, cr2)
    assert (await _store(session, world)).courier_radius_km is None


async def test_omitted_courier_radius_is_left_alone(session: AsyncSession) -> None:
    world = await seed_courier_world(session)  # courier 500 km
    cr = await _create(session, world, G.StoreBasics, {"delivery_radius_km": 6})
    await _approve(session, cr)
    store = await _store(session, world)
    assert (store.delivery_radius_km, store.courier_radius_km) == (6, 500)


async def test_courier_radius_checked_against_local_at_submission(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    with pytest.raises(HTTPException) as small:
        await _create(session, world, G.StoreBasics, {"delivery_radius_km": 10, "courier_radius_km": 8})
    assert small.value.status_code == 422 and small.value.detail == "courier_radius_not_larger"
    await session.rollback()
    with pytest.raises(HTTPException) as widened:
        # Raising only the local radius past the stored 500 km ring.
        await _create(session, world, G.StoreBasics, {"delivery_radius_km": 50, "courier_radius_km": 40})
    assert widened.value.detail == "courier_radius_not_larger"


async def test_courier_radius_rechecked_at_approval(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    cr = await _create(session, world, G.StoreBasics, {"delivery_radius_km": 5, "courier_radius_km": 600})
    with pytest.raises(HTTPException) as exc:
        await approve(
            session=session, cr=cr, admin_user_id=ADMIN_ID,
            applied={"delivery_radius_km": 40, "courier_radius_km": 20},
        )
    assert exc.value.detail == "courier_radius_not_larger"


async def test_services_row_carries_courier_enabled(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    row = {"service_id": world.service_id, "free_delivery_threshold": 500, "delivery_fee": 30}
    cr = await _create(session, world, G.Services, {"services": [{**row, "courier_enabled": False}]})
    assert cr.baseline_json["services"][0]["courier_enabled"] is True
    await _approve(session, cr)
    sps = await session.get(SellerProfileService, world.sps_id)
    assert sps is not None
    await session.refresh(sps)
    assert sps.courier_enabled is False
    cr2 = await _create(session, world, G.Services, {"services": [row]})  # omitted → unchanged
    await _approve(session, cr2)
    await session.refresh(sps)
    assert sps.courier_enabled is False


async def test_banking_carries_bank_transfer_fields(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    cr = await _create(session, world, G.Banking, {
        "bank_account_number": "999988887777", "bank_ifsc": "ICIC0004321",
        "bank_account_name": "Ravi Sweets Pvt Ltd", "bank_transfer_enabled": True,
    })
    assert cr.baseline_json["bank_transfer_enabled"] is True
    await _approve(session, cr)
    profile = await session.get(SellerProfile, world.seller_profile_id)
    assert profile is not None
    await session.refresh(profile)
    assert profile.bank_account_name == "Ravi Sweets Pvt Ltd"
    cr2 = await _create(session, world, G.Banking, {
        "bank_account_number": "111122223333", "bank_ifsc": "ICIC0004321",
    })
    await _approve(session, cr2)
    await session.refresh(profile)
    assert (profile.bank_account_name, profile.bank_transfer_enabled) == ("Ravi Sweets Pvt Ltd", True)


async def test_banking_rejects_an_incomplete_bank_transfer(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    with pytest.raises(HTTPException) as exc:
        await _create(session, world, G.Banking, {
            "bank_account_number": "999988887777", "bank_ifsc": "ICIC0004321",
            "bank_account_name": "", "bank_transfer_enabled": True,
        })
    assert exc.value.status_code == 422 and exc.value.detail == "bank_transfer_incomplete"
