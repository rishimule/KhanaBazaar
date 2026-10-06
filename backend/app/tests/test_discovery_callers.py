# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Door checkout and the admin address override answer exactly as before
after moving onto services/serviceability.py."""
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.store import Store
from tests._courier_helpers import CUSTOMER, client_as, seed_courier_world


async def _place_door(world, address_id: int):  # type: ignore[no-untyped-def]
    async with client_as(CUSTOMER) as ac:
        return await ac.post("/api/v1/orders", json={
            "customer_address_id": address_id,
            "store_id": world.store_id,
            "service_id": world.service_id,
            "payment_method": "upi",
            "delivery_mode": "door_delivery",
        })


async def test_door_checkout_outside_the_radius_still_422(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    resp = await _place_door(world, world.far_address_id)
    assert resp.status_code == 422 and resp.json()["detail"] == "outside_delivery_area"


async def test_door_checkout_at_an_inactive_store_is_still_store_unavailable(
    session: AsyncSession,
) -> None:
    world = await seed_courier_world(session)
    store = await session.get(Store, world.store_id)
    assert store is not None
    store.is_active = False
    await session.commit()
    resp = await _place_door(world, world.local_address_id)
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["detail"] == "store_unavailable"


async def test_door_checkout_inside_the_radius_still_places(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    resp = await _place_door(world, world.local_address_id)
    assert resp.status_code == 201, resp.text
