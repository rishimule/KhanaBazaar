# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""A favourite only a courier store ships is no longer "unavailable"."""
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Favorite
from app.models.profile import SellerProfileService
from app.models.store import Store
from tests._courier_helpers import COURIER_POINT, CUSTOMER, FAR_POINT, client_as
from tests._discovery_helpers import seed_discovery_extras, seed_discovery_world


async def _grouped(point: tuple[float, float]) -> dict[str, Any]:
    async with client_as(CUSTOMER) as ac:
        resp = await ac.get("/api/v1/favorites/", params={"lat": point[0], "lng": point[1]})
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def test_courier_only_favourites_get_courier_store_groups(session: AsyncSession) -> None:
    world = await seed_discovery_world(session)
    session.add_all([
        Favorite(customer_profile_id=world.courier.customer_profile_id, product_id=world.kaju_id),
        Favorite(customer_profile_id=world.courier.customer_profile_id, product_id=world.soan_id),
    ])
    await session.commit()
    mysuru = await _grouped(COURIER_POINT)
    assert [
        (g["store_name"], g["fulfilment"], [i["product_id"] for i in g["items"]])
        for g in mysuru["groups"]
    ] == [
        ("Mysuru Mart", "local", [world.kaju_id]),  # sold locally: not repeated under Ravi
        ("Ravi Sweets", "courier", [world.soan_id]),
    ]
    assert mysuru["unavailable"] == []
    delhi = await _grouped(FAR_POINT)
    assert delhi["groups"] == []
    assert {p["product_id"] for p in delhi["unavailable"]} == {world.kaju_id, world.soan_id}


async def _favourite(session: AsyncSession, customer_profile_id: int, *product_ids: int) -> None:
    session.add_all([
        Favorite(customer_profile_id=customer_profile_id, product_id=pid) for pid in product_ids
    ])
    await session.commit()


async def test_courier_favourites_only_for_a_service_that_ships(session: AsyncSession) -> None:
    world = await seed_discovery_world(session)
    extras = await seed_discovery_extras(session, world)
    await _favourite(session, world.courier.customer_profile_id, world.soan_id, extras.sev_id)
    mysuru = await _grouped(COURIER_POINT)
    # Ravi ships Sweets, not Namkeen: Ratlami Sev stays unavailable at Mysuru.
    assert [(g["store_name"], [i["product_id"] for i in g["items"]]) for g in mysuru["groups"]] == [
        ("Ravi Sweets", [world.soan_id]),
    ]
    assert [p["product_id"] for p in mysuru["unavailable"]] == [extras.sev_id]


async def test_local_groups_lead_even_when_a_courier_store_is_nearer(
    session: AsyncSession,
) -> None:
    world = await seed_discovery_world(session)
    extras = await seed_discovery_extras(session, world)
    # Ravi (~128 km) becomes local; Mysuru Mart (~0.4 km) becomes courier-only.
    ravi = await session.get(Store, world.ravi_store_id)
    mysuru = await session.get(Store, world.mysuru_store_id)
    assert ravi is not None and mysuru is not None
    ravi.delivery_radius_km = 200.0
    mysuru.delivery_radius_km = 0.1
    mysuru.courier_radius_km = 50.0
    mysuru_sweets = (
        await session.exec(
            select(SellerProfileService).where(
                SellerProfileService.seller_profile_id == mysuru.seller_profile_id
            )
        )
    ).one()
    mysuru_sweets.courier_enabled = True
    await session.commit()
    await _favourite(session, world.courier.customer_profile_id, world.kaju_id, extras.mysore_pak_id)
    groups = (await _grouped(COURIER_POINT))["groups"]
    assert [(g["store_name"], g["fulfilment"], [i["product_id"] for i in g["items"]]) for g in groups] == [
        ("Ravi Sweets", "local", [world.kaju_id]),
        ("Mysuru Mart", "courier", [extras.mysore_pak_id]),
    ]
    assert groups[0]["distance_km"] > groups[1]["distance_km"]

