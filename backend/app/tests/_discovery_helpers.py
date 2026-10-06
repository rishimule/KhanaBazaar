# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Phase B (discovery) test world: the Phase A courier world plus a store
that is local to Mysuru.

At COURIER_POINT (Mysuru): Mysuru Mart is local, Ravi Sweets is courier (its
500 km ring; Sweets ships), Mira Mart is neither. At LOCAL_POINT (Bengaluru):
Ravi Sweets and Mira Mart are local, Mysuru Mart is neither.

Products, all in the Sweets service:
- Kaju Katli: Ravi ₹100, Mysuru Mart ₹120, Mira Mart ₹90;
- Soan Papdi: Ravi only, ₹80.
"""
from dataclasses import dataclass

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import MasterProduct, MasterProductTranslation
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from app.models.store import Store, StoreInventory
from tests._courier_helpers import CourierWorld, seed_courier_world
from tests._helpers import make_address

MYSURU_STORE_POINT = (12.2990, 76.6400)  # ~0.4 km from COURIER_POINT
MYSURU_SELLER = User(
    id=8106, email="mysuru-seller@kb.test", role=UserRole.Seller, is_active=True
)


@dataclass(frozen=True)
class DiscoveryWorld:
    courier: CourierWorld
    ravi_store_id: int
    mira_store_id: int
    mysuru_store_id: int
    service_id: int
    kaju_id: int
    soan_id: int


async def _mysuru_address(session: AsyncSession, pincode: str) -> Address:
    addr = Address(
        **make_address(
            latitude=MYSURU_STORE_POINT[0], longitude=MYSURU_STORE_POINT[1],
            pincode=pincode, city="Mysuru", state="Karnataka",
        )
    )
    session.add(addr)
    await session.flush()
    return addr


async def seed_discovery_world(session: AsyncSession) -> DiscoveryWorld:
    world = await seed_courier_world(session)
    inventory = await session.get(StoreInventory, world.inventory_id)
    assert inventory is not None
    kaju = await session.get(MasterProduct, inventory.product_id)
    assert kaju is not None and kaju.id is not None
    mira = (await session.exec(select(Store).where(Store.name == "Mira Mart"))).one()
    assert mira.id is not None
    kaju_id, mira_id, subcategory_id = kaju.id, mira.id, kaju.subcategory_id

    session.add(User(**MYSURU_SELLER.model_dump()))
    await session.flush()
    business = await _mysuru_address(session, "570002")
    seller = SellerProfile(
        user_id=MYSURU_SELLER.id, first_name="Lata", phone="+919900000006",
        business_name="Mysuru Mart", verification_status=VerificationStatus.Approved,
        business_address_id=business.id, upi_vpa="lata@okaxis", upi_enabled=True,
    )
    session.add(seller)
    await session.flush()
    store_address = await _mysuru_address(session, "570003")
    mysuru = Store(
        name="Mysuru Mart", seller_profile_id=seller.id, address_id=store_address.id,
        delivery_radius_km=10.0, pin_confirmed=True,
    )
    session.add(mysuru)
    await session.flush()
    assert mysuru.id is not None
    session.add(SellerProfileService(seller_profile_id=seller.id, service_id=world.service_id))

    soan = MasterProduct(subcategory_id=subcategory_id, slug="soan-papdi", base_price=80.0)
    session.add(soan)
    await session.flush()
    assert soan.id is not None
    session.add(
        MasterProductTranslation(
            master_product_id=soan.id, language_code="en",
            name="Soan Papdi", description="250 g box",
        )
    )
    session.add_all([
        StoreInventory(store_id=mysuru.id, product_id=kaju_id, price=120.0, stock=10, is_available=True),
        StoreInventory(store_id=mira_id, product_id=kaju_id, price=90.0, stock=10, is_available=True),
        StoreInventory(store_id=world.store_id, product_id=soan.id, price=80.0, stock=10, is_available=True),
    ])
    ids = DiscoveryWorld(
        courier=world, ravi_store_id=world.store_id, mira_store_id=mira_id,
        mysuru_store_id=mysuru.id, service_id=world.service_id,
        kaju_id=kaju_id, soan_id=soan.id,
    )
    await session.commit()
    return ids
