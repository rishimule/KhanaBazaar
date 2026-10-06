# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""GET /stores/?lat&lng: local stores, then courier stores (spec §12)."""
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Service
from app.models.platform_fee import ArrangementStatus, FeeArrangement, FeeModel
from app.models.profile import SellerProfileService
from app.models.store import Store
from tests._courier_helpers import COURIER_POINT, CUSTOMER, LOCAL_POINT, client_as
from tests._discovery_helpers import seed_discovery_world


async def _list(point: tuple[float, float], **params: Any) -> list[dict[str, Any]]:
    async with client_as(CUSTOMER) as ac:
        resp = await ac.get(
            "/api/v1/stores/",
            params={"lat": point[0], "lng": point[1], "sort": "distance", **params},
        )
    assert resp.status_code == 200, resp.text
    rows: list[dict[str, Any]] = resp.json()
    return rows


async def test_local_stores_then_courier_stores(session: AsyncSession) -> None:
    world = await seed_discovery_world(session)
    rows = await _list(COURIER_POINT)
    assert [(r["name"], r["fulfilment"]) for r in rows] == [
        ("Mysuru Mart", "local"), ("Ravi Sweets", "courier"),
    ]
    assert rows[1]["courier_service_ids"] == [world.service_id]
    assert rows[0]["courier_service_ids"] == []
    home = await _list(LOCAL_POINT)
    assert {r["fulfilment"] for r in home} == {"local"}


async def test_local_comes_first_even_when_a_courier_store_is_nearer(
    session: AsyncSession,
) -> None:
    world = await seed_discovery_world(session)
    # Ravi Sweets (~128 km away) becomes local by widening its radius; Mysuru
    # Mart (~0.4 km away) becomes courier-only. The far local store must lead.
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
    rows = await _list(COURIER_POINT)
    assert [(r["name"], r["fulfilment"]) for r in rows] == [
        ("Ravi Sweets", "local"), ("Mysuru Mart", "courier"),
    ]
    assert rows[0]["distance_km"] > rows[1]["distance_km"]


async def test_service_filter_needs_the_service_to_ship(session: AsyncSession) -> None:
    world = await seed_discovery_world(session)
    snacks = Service(slug="snacks", is_active=True)
    session.add(snacks)
    await session.flush()
    ravi = await session.get(Store, world.ravi_store_id)
    mysuru = await session.get(Store, world.mysuru_store_id)
    assert ravi is not None and mysuru is not None and snacks.id is not None
    # Both offer snacks; Ravi does NOT ship snacks by courier.
    session.add_all([
        SellerProfileService(seller_profile_id=ravi.seller_profile_id, service_id=snacks.id),
        SellerProfileService(seller_profile_id=mysuru.seller_profile_id, service_id=snacks.id),
    ])
    await session.commit()
    sweets = await _list(COURIER_POINT, service="sweets")
    assert [r["name"] for r in sweets] == ["Mysuru Mart", "Ravi Sweets"]
    snack_rows = await _list(COURIER_POINT, service="snacks")
    assert [r["name"] for r in snack_rows] == ["Mysuru Mart"]


async def test_radius_cap_applies_to_both_zones(session: AsyncSession) -> None:
    await seed_discovery_world(session)
    # A fractional cap also proves :user_cap is bound as a float, not an int.
    rows = await _list(COURIER_POINT, radius_km=50.5)
    assert [r["name"] for r in rows] == ["Mysuru Mart"]  # Ravi is ~128 km away


async def test_list_without_a_location_has_no_fulfilment(session: AsyncSession) -> None:
    await seed_discovery_world(session)
    async with client_as(CUSTOMER) as ac:
        resp = await ac.get("/api/v1/stores/")
    assert resp.status_code == 200
    assert {r["fulfilment"] for r in resp.json()} == {None}


async def test_a_fee_suspended_store_does_not_leave_a_page_short(session: AsyncSession) -> None:
    world = await seed_discovery_world(session)
    assert world.ravi_store_id < world.mira_store_id  # id order puts Ravi first
    session.add(FeeArrangement(
        store_id=world.ravi_store_id, service_id=world.service_id,
        model=FeeModel.Freebie, status=ArrangementStatus.Suspended,
    ))
    await session.commit()
    # Without `sort` the list is in id order, so Ravi Sweets (suspended) would
    # take the only slot if it were filtered after LIMIT.
    async with client_as(CUSTOMER) as ac:
        resp = await ac.get("/api/v1/stores/", params={
            "lat": LOCAL_POINT[0], "lng": LOCAL_POINT[1], "service": "sweets", "limit": 1,
        })
    assert resp.status_code == 200, resp.text
    assert [r["name"] for r in resp.json()] == ["Mira Mart"]

