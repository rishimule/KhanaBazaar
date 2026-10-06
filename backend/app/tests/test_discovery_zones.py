# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""The zone rule as listing SQL and as a per-point Locality (spec §5, §12)."""
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Service
from app.models.profile import SellerProfile
from app.models.store import Store
from app.services.serviceability import (
    Locality,
    compute_locality,
    courier_enabled_service_ids,
    within_local_radius,
    zone_case_sql,
    zone_params,
)
from tests._courier_helpers import COURIER_POINT, FAR_POINT, LOCAL_POINT
from tests._discovery_helpers import seed_discovery_world

MALE = (4.1755, 73.5093)  # Maldives: ~1,080 km from Bengaluru, outside the India box


async def _zones(
    session: AsyncSession, point: tuple[float, float], service_id: int | None = None
) -> dict[str, str | None]:
    expr = ":service_id" if service_id is not None else None
    params: dict[str, object] = {**zone_params(*point)}
    if service_id is not None:
        params["service_id"] = service_id
    rows = (
        await session.execute(
            text(
                f"SELECT s.name, {zone_case_sql(expr)} AS zone FROM store s "
                "JOIN address a ON a.id = s.address_id "
                "JOIN sellerprofile sp ON sp.id = s.seller_profile_id "
                "WHERE s.is_active AND a.geo IS NOT NULL"
            ),
            params,
        )
    ).all()
    return {r.name: r.zone for r in rows}


async def test_zone_case_follows_the_rule(session: AsyncSession) -> None:
    await seed_discovery_world(session)
    assert await _zones(session, COURIER_POINT) == {
        "Ravi Sweets": "courier", "Mira Mart": None, "Mysuru Mart": "local",
    }
    at_home = await _zones(session, LOCAL_POINT)
    assert (at_home["Ravi Sweets"], at_home["Mira Mart"], at_home["Mysuru Mart"]) == (
        "local", "local", None,
    )
    assert set((await _zones(session, FAR_POINT)).values()) == {None}


async def test_zone_case_needs_the_service_to_ship_and_a_payee(session: AsyncSession) -> None:
    world = await seed_discovery_world(session)
    snacks = Service(slug="snacks", is_active=True)
    session.add(snacks)
    await session.commit()
    assert snacks.id is not None
    assert (await _zones(session, COURIER_POINT, snacks.id))["Ravi Sweets"] is None
    assert (await _zones(session, COURIER_POINT, world.service_id))["Ravi Sweets"] == "courier"
    seller = await session.get(SellerProfile, world.courier.seller_profile_id)
    assert seller is not None
    seller.upi_enabled = False
    seller.bank_transfer_enabled = False
    await session.commit()
    assert (await _zones(session, COURIER_POINT))["Ravi Sweets"] is None


async def test_a_point_outside_india_is_never_courier(session: AsyncSession) -> None:
    world = await seed_discovery_world(session)
    store = await session.get(Store, world.ravi_store_id)
    assert store is not None
    store.courier_radius_km = 3500.0
    await session.commit()
    assert (await _zones(session, MALE))["Ravi Sweets"] is None


async def test_within_local_radius_ignores_store_status(session: AsyncSession) -> None:
    world = await seed_discovery_world(session)
    store = await session.get(Store, world.ravi_store_id)
    assert store is not None
    store.is_active = False
    await session.commit()
    assert await within_local_radius(
        session, store_id=world.ravi_store_id, lat=LOCAL_POINT[0], lng=LOCAL_POINT[1]
    )
    assert not await within_local_radius(
        session, store_id=world.ravi_store_id, lat=COURIER_POINT[0], lng=COURIER_POINT[1]
    )


async def test_compute_locality(session: AsyncSession) -> None:
    world = await seed_discovery_world(session)
    mysuru = await compute_locality(session, lat=COURIER_POINT[0], lng=COURIER_POINT[1])
    assert mysuru.local == (world.mysuru_store_id,)
    assert mysuru.courier == {world.service_id: (world.ravi_store_id,)}
    assert mysuru.fulfilment(world.ravi_store_id, world.service_id) == "courier"
    assert mysuru.fulfilment(world.ravi_store_id) == "courier"
    assert mysuru.fulfilment(world.ravi_store_id, 99999) is None
    assert mysuru.fulfilment(world.mysuru_store_id, world.service_id) == "local"
    assert mysuru.fulfilment(world.mira_store_id) is None
    assert Locality.from_json(mysuru.to_json()) == mysuru
    home = await compute_locality(session, lat=LOCAL_POINT[0], lng=LOCAL_POINT[1])
    assert set(home.local) == {world.ravi_store_id, world.mira_store_id}
    assert home.courier == {}  # a store local to the point is never listed as courier
    far = await compute_locality(session, lat=FAR_POINT[0], lng=FAR_POINT[1])
    assert far.is_empty


async def test_courier_enabled_service_ids(session: AsyncSession) -> None:
    world = await seed_discovery_world(session)
    shipping = await courier_enabled_service_ids(
        session, [world.ravi_store_id, world.mira_store_id]
    )
    assert shipping == {world.ravi_store_id: (world.service_id,)}
    assert await courier_enabled_service_ids(session, []) == {}
