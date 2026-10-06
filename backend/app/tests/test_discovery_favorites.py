# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""A favourite only a courier store ships is no longer "unavailable"."""
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Favorite
from tests._courier_helpers import COURIER_POINT, CUSTOMER, FAR_POINT, client_as
from tests._discovery_helpers import seed_discovery_world


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
