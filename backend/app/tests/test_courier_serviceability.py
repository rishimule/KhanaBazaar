# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.commerce import PaymentMethod
from app.models.profile import SellerProfile, SellerProfileService
from app.models.store import Store
from app.services.serviceability import (
    StoreZone,
    courier_payment_methods,
    is_courier_destination,
    zone_for_point,
)
from tests._courier_helpers import (
    COURIER_POINT,
    CUSTOMER,
    FAR_POINT,
    LOCAL_POINT,
    STORE_POINT,
    CourierWorld,
    client_as,
    seed_courier_world,
)
from tests._helpers import make_address


async def _zone(
    session: AsyncSession, world: CourierWorld, point: tuple[float, float], **kw: object
) -> StoreZone:
    return await zone_for_point(
        session, store_id=world.store_id, lat=point[0], lng=point[1], **kw  # type: ignore[arg-type]
    )


async def test_three_zones(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    local = await _zone(session, world, LOCAL_POINT)
    courier = await _zone(session, world, COURIER_POINT)
    far = await _zone(session, world, FAR_POINT)
    assert local.zone == "local" and local.distance_km is not None and local.distance_km < 5
    assert courier.zone == "courier"
    assert courier.courier_service_ids == (world.service_id,)
    assert far.zone == "none"


async def test_service_filter(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    assert (await _zone(session, world, COURIER_POINT, service_id=world.service_id)).zone == "courier"
    assert (await _zone(session, world, COURIER_POINT, service_id=world.service_id + 999)).zone == "none"


async def test_no_courier_without_radius_or_switch(session: AsyncSession) -> None:
    world = await seed_courier_world(session, courier_radius_km=None)
    assert (await _zone(session, world, COURIER_POINT)).zone == "none"
    store = await session.get(Store, world.store_id)
    assert store is not None
    store.courier_radius_km = 500.0
    sps = await session.get(SellerProfileService, world.sps_id)
    assert sps is not None
    sps.courier_enabled = False
    await session.commit()
    assert (await _zone(session, world, COURIER_POINT)).zone == "none"


async def test_no_courier_without_a_live_payee(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    seller.upi_enabled = False
    seller.bank_transfer_enabled = False
    await session.commit()
    assert (await _zone(session, world, COURIER_POINT)).zone == "none"
    seller.bank_transfer_enabled = True
    await session.commit()
    assert courier_payment_methods(seller) == [PaymentMethod.NetBanking]
    assert (await _zone(session, world, COURIER_POINT)).zone == "courier"


async def test_incomplete_bank_details_do_not_count(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    seller.bank_account_name = None
    assert courier_payment_methods(seller) == [PaymentMethod.Upi]


async def test_local_boundary_is_inclusive(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    distance_km = float((await session.exec(text(  # type: ignore[call-overload]
        "SELECT ST_Distance(a.geo, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography) / 1000.0 "
        "FROM store s JOIN address a ON a.id = s.address_id WHERE s.id = :sid"
    ).bindparams(lat=COURIER_POINT[0], lng=COURIER_POINT[1], sid=world.store_id))).scalar_one())
    store = await session.get(Store, world.store_id)
    assert store is not None
    store.delivery_radius_km = distance_km + 0.001
    await session.commit()
    assert (await _zone(session, world, COURIER_POINT)).zone == "local"
    store.delivery_radius_km = distance_km - 0.001
    await session.commit()
    assert (await _zone(session, world, COURIER_POINT)).zone == "courier"


async def test_inactive_store_and_missing_geo_are_none(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    store = await session.get(Store, world.store_id)
    assert store is not None
    store.is_active = False
    await session.commit()
    assert (await _zone(session, world, LOCAL_POINT)).zone == "none"
    store.is_active = True
    addr = await session.get(Address, store.address_id)
    assert addr is not None
    addr.latitude = None
    addr.longitude = None
    await session.commit()
    assert (await _zone(session, world, LOCAL_POINT)).zone == "none"


async def test_paused_store_keeps_its_zone(session: AsyncSession) -> None:
    # Availability is enforced at checkout, not by the zone (spec §5.1).
    world = await seed_courier_world(session)
    store = await session.get(Store, world.store_id)
    assert store is not None
    store.is_paused = True
    await session.commit()
    assert (await _zone(session, world, COURIER_POINT)).zone == "courier"


async def test_point_outside_india_bbox_is_none(session: AsyncSession) -> None:
    world = await seed_courier_world(session, courier_radius_km=3000.0)
    male = (4.1755, 73.5093)  # Malé, Maldives — inside 3,000 km, outside the bbox
    assert (await _zone(session, world, male)).zone == "none"


def test_courier_destination_requires_india_and_six_digit_pin() -> None:
    assert is_courier_destination(Address(**make_address(pincode="570001")))
    assert not is_courier_destination(Address(**make_address(pincode="57001")))
    assert not is_courier_destination(Address(**make_address(pincode="44600", country="Nepal")))


async def test_endpoint_reports_zone_and_keeps_serviceable_local_only(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    async with client_as(CUSTOMER) as ac:
        courier = await ac.post("/api/v1/geo/serviceability", json={
            "lat": COURIER_POINT[0], "lng": COURIER_POINT[1],
            "store_id": world.store_id, "service_id": world.service_id,
        })
        local = await ac.post("/api/v1/geo/serviceability", json={
            "lat": STORE_POINT[0], "lng": STORE_POINT[1], "store_id": world.store_id,
        })
        count = await ac.post("/api/v1/geo/serviceability", json={
            "lat": STORE_POINT[0], "lng": STORE_POINT[1],
        })
    assert courier.status_code == 200, courier.text
    assert courier.json() == {
        "serviceable": False, "store_count": None,
        "zone": "courier", "courier_service_ids": [world.service_id],
    }
    assert local.json()["serviceable"] is True and local.json()["zone"] == "local"
    assert count.json()["serviceable"] is True and count.json()["zone"] is None
