# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.dev_seed import seed_demo_data
from app.models.address import Address
from app.models.profile import CustomerAddress, SellerProfile, SellerProfileService
from app.models.store import Store
from app.services.serviceability import zone_for_point


async def test_seed_has_a_courier_store_reaching_pune(session: AsyncSession) -> None:
    await seed_demo_data(session)
    store = (await session.exec(select(Store).where(Store.name == "Krishna Supermart"))).one()
    assert store.courier_radius_km == 1500.0
    rows = (
        await session.exec(
            select(SellerProfileService).where(
                SellerProfileService.seller_profile_id == store.seller_profile_id
            )
        )
    ).all()
    assert rows and all(r.courier_enabled for r in rows)
    seller = await session.get(SellerProfile, store.seller_profile_id)
    assert seller is not None and seller.bank_transfer_enabled is True
    pune = (
        await session.exec(
            select(Address)
            .join(CustomerAddress, CustomerAddress.address_id == Address.id)  # type: ignore[arg-type]
            .where(CustomerAddress.label == "Pune Trip")
        )
    ).first()
    assert pune is not None and pune.latitude is not None and pune.longitude is not None
    assert store.id is not None
    zone = await zone_for_point(session, store_id=store.id, lat=pune.latitude, lng=pune.longitude)
    assert zone.zone == "courier"


async def test_courier_seed_is_idempotent(session: AsyncSession) -> None:
    await seed_demo_data(session)
    await seed_demo_data(session)
    store = (await session.exec(select(Store).where(Store.name == "Krishna Supermart"))).one()
    assert store.courier_radius_km == 1500.0
