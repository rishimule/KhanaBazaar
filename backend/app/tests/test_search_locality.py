# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from fakeredis.aioredis import FakeRedis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import SellerProfile, VerificationStatus
from app.models.store import Store
from app.search.locality import (
    get_serviceable_store_ids,
    grid_cell_key,
    in_india_bbox,
)
from tests._helpers import make_address


def test_grid_cell_key_rounds_to_500m():
    assert grid_cell_key(19.0744, 72.8769) == grid_cell_key(19.07442, 72.87692)


def test_in_india_bbox():
    assert in_india_bbox(19.07, 72.87) is True
    assert in_india_bbox(60.0, 70.0) is False
    assert in_india_bbox(20.0, 130.0) is False


async def _seed_store(
    session: AsyncSession, *, lat: float, lng: float, radius_km: float, uid: int
):
    user = User(
        id=uid, email=f"loc-{uid}@kb.com", role=UserRole.Seller, is_active=True
    )
    session.add(user)
    await session.flush()
    biz_addr = Address(**make_address(pincode="100001"))
    session.add(biz_addr)
    await session.flush()
    seller = SellerProfile(
        user_id=user.id, first_name="S", phone=f"+9198{uid:06d}",
        business_name="X", bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz_addr.id,
    )
    session.add(seller)
    await session.flush()
    store_addr = Address(**make_address(latitude=lat, longitude=lng, pincode="100002"))
    session.add(store_addr)
    await session.flush()
    store = Store(
        name=f"Store-{uid}",
        seller_profile_id=seller.id,
        address_id=store_addr.id,
        is_active=True,
        delivery_radius_km=radius_km,
    )
    session.add(store)
    await session.flush()
    store_id = store.id
    await session.commit()
    return store_id


@pytest.mark.asyncio
async def test_returns_stores_within_radius(session: AsyncSession):
    near_id = await _seed_store(session, lat=19.07, lng=72.87, radius_km=5, uid=801)
    far_id = await _seed_store(session, lat=20.00, lng=73.50, radius_km=3, uid=802)
    redis = FakeRedis(decode_responses=True)
    ids = await get_serviceable_store_ids(session, redis, lat=19.075, lng=72.875)
    assert ids is not None
    assert near_id in ids
    assert far_id not in ids


@pytest.mark.asyncio
async def test_cache_hit_skips_postgres(session: AsyncSession, monkeypatch):
    await _seed_store(session, lat=19.07, lng=72.87, radius_km=5, uid=803)
    redis = FakeRedis(decode_responses=True)

    calls = {"n": 0}
    original = session.execute

    async def counting_execute(*a, **kw):
        calls["n"] += 1
        return await original(*a, **kw)

    monkeypatch.setattr(session, "execute", counting_execute)
    await get_serviceable_store_ids(session, redis, lat=19.075, lng=72.875)
    after_first = calls["n"]
    await get_serviceable_store_ids(session, redis, lat=19.075, lng=72.875)
    assert calls["n"] == after_first  # second call hit redis only


@pytest.mark.asyncio
async def test_none_when_no_lat_lng(session: AsyncSession):
    redis = FakeRedis(decode_responses=True)
    assert await get_serviceable_store_ids(session, redis, lat=None, lng=None) is None


@pytest.mark.asyncio
async def test_none_when_out_of_india(session: AsyncSession):
    redis = FakeRedis(decode_responses=True)
    assert await get_serviceable_store_ids(session, redis, lat=40.0, lng=-74.0) is None
