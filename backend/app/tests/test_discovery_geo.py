# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Count-mode POST /geo/serviceability adds courier_store_count (spec §12)."""
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from tests._courier_helpers import (
    COURIER_POINT,
    CUSTOMER,
    FAR_POINT,
    LOCAL_POINT,
    client_as,
)
from tests._discovery_helpers import seed_discovery_world


async def _count(point: tuple[float, float]) -> dict[str, Any]:
    async with client_as(CUSTOMER) as ac:
        resp = await ac.post("/api/v1/geo/serviceability", json={"lat": point[0], "lng": point[1]})
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def test_count_mode_reports_local_and_courier_stores(session: AsyncSession) -> None:
    await seed_discovery_world(session)
    mysuru = await _count(COURIER_POINT)
    assert (mysuru["serviceable"], mysuru["store_count"], mysuru["courier_store_count"]) == (True, 1, 1)
    home = await _count(LOCAL_POINT)
    assert (home["store_count"], home["courier_store_count"]) == (2, 0)
    delhi = await _count(FAR_POINT)
    assert (delhi["serviceable"], delhi["store_count"], delhi["courier_store_count"]) == (False, 0, 0)
