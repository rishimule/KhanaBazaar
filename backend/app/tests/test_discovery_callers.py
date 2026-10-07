# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Door checkout and the admin address override answer exactly as before
after moving onto services/serviceability.py."""
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Order
from app.models.store import Store
from tests._courier_helpers import ADMIN, CUSTOMER, client_as, seed_courier_world
from tests._helpers import make_address


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


async def test_admin_override_inside_the_radius_still_succeeds(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    placed = await _place_door(world, world.local_address_id)
    assert placed.status_code == 201, placed.text
    moved = make_address(
        address_line1="7 Brigade Road", city="Bengaluru", state="Karnataka",
        pincode="560025", latitude=12.9740, longitude=77.6070,  # ~1.4 km from the store
    )
    async with client_as(ADMIN) as ac:
        resp = await ac.patch(
            f"/api/v1/admin/orders/{placed.json()['id']}/delivery-address",
            json={"address": moved, "reason": "customer moved two streets over"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "updated"}
    order = await session.get(Order, placed.json()["id"])
    assert order is not None
    await session.refresh(order)
    assert "7 Brigade Road" in order.delivery_address_snapshot

