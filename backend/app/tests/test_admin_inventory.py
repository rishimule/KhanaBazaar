# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Backend coverage for admin-on-behalf-of-seller inventory writes.

Every admin write must:
- mutate inventory exactly like the seller path would
- emit one ``AdminActionLog`` row of the correct ``action`` and diff
- enforce reason-required gates on destructive actions
- reject when the seller is not Approved (409 ``seller_not_active``)
"""
from typing import AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_seller, get_current_user
from app.models.address import Address
from app.models.admin_audit import AdminActionLog
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    MasterProduct,
    Service,
    ServiceTranslation,
    Subcategory,
)
from app.models.profile import (
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

mock_admin = User(id=701, email="admin-inv@kb.com", role=UserRole.Admin, is_active=True)
mock_seller = User(id=702, email="seller-inv@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture(autouse=True)
async def seed_admin_inventory(session: AsyncSession) -> AsyncGenerator[dict, None]:
    session.add(User(**mock_admin.model_dump()))
    session.add(User(**mock_seller.model_dump()))
    await session.flush()

    biz_address = Address(**make_address())
    session.add(biz_address)
    store_address = Address(**make_address(latitude=28.50, longitude=77.10))
    session.add(store_address)
    await session.flush()

    seller_profile = SellerProfile(
        user_id=mock_seller.id,
        first_name="Inv",
        business_name="Inv Test Store",
        phone="+919800000701",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz_address.id,
    )
    session.add(seller_profile)
    await session.flush()

    grocery = Service(slug="inv-grocery")
    session.add(grocery)
    await session.flush()
    session.add(
        ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery")
    )
    session.add(
        SellerProfileService(
            seller_profile_id=seller_profile.id, service_id=grocery.id
        )
    )

    cat = Category(slug="inv-cat", service_id=grocery.id, is_active=True)
    session.add(cat)
    await session.flush()
    sub = Subcategory(slug="inv-sub", category_id=cat.id, is_active=True)
    session.add(sub)
    await session.flush()
    product = MasterProduct(
        slug="inv-test-atta",
        subcategory_id=sub.id,
        base_price=100.0,
        is_active=True,
    )
    session.add(product)
    await session.flush()

    store = Store(
        name="Inv Test Store",
        seller_profile_id=seller_profile.id,
        address_id=store_address.id,
        delivery_radius_km=5.0,
        is_active=True,
    )
    session.add(store)
    await session.flush()

    inv = StoreInventory(
        store_id=store.id,
        product_id=product.id,
        price=100.0,
        stock=10,
        is_available=True,
    )
    session.add(inv)
    await session.flush()
    ids = {
        "seller_profile_id": seller_profile.id,
        "store_id": store.id,
        "product_id": product.id,
        "inv_id": inv.id,
        "subcategory_id": sub.id,
    }
    await session.commit()

    yield ids


@pytest.fixture
def override_as_admin() -> Iterator[None]:
    app.dependency_overrides[get_current_admin] = lambda: mock_admin
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    yield None
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_as_seller() -> Iterator[None]:
    app.dependency_overrides[get_current_seller] = lambda: mock_seller
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    yield None
    app.dependency_overrides.pop(get_current_seller, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_update_inventory_writes_audit_row_with_diff(
    seed_admin_inventory: dict,
    override_as_admin: None,
    session: AsyncSession,
) -> None:
    s = seed_admin_inventory
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/api/v1/stores/{s['store_id']}/inventory/{s['inv_id']}",
            json={
                "product_id": s["product_id"],
                "price": 250.0,
                "stock": 7,
                "is_available": True,
            },
        )
    assert resp.status_code == 200, resp.text

    rows = list((await session.exec(select(AdminActionLog))).all())
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "inventory.update"
    assert row.before_json["price"] == 100.0
    assert row.after_json["price"] == 250.0


@pytest.mark.asyncio
async def test_admin_create_inventory_audits_with_real_target_id(
    seed_admin_inventory: dict,
    override_as_admin: None,
    session: AsyncSession,
) -> None:
    s = seed_admin_inventory
    # Need a NEW product (the seeded one is already in inventory).
    new_product = MasterProduct(
        slug="inv-test-dal",
        subcategory_id=s["subcategory_id"],
        base_price=80.0,
        is_active=True,
    )
    session.add(new_product)
    await session.flush()
    new_product_id = new_product.id
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/v1/stores/{s['store_id']}/inventory",
            json={
                "product_id": new_product_id,
                "price": 80.0,
                "stock": 4,
                "is_available": True,
            },
        )
    assert resp.status_code == 200, resp.text
    new_inv_id = resp.json()["id"]

    rows = list((await session.exec(select(AdminActionLog))).all())
    assert len(rows) == 1
    assert rows[0].action == "inventory.create"
    assert rows[0].target_id == new_inv_id


@pytest.mark.asyncio
async def test_admin_delete_inventory_requires_reason(
    seed_admin_inventory: dict,
    override_as_admin: None,
    session: AsyncSession,
) -> None:
    s = seed_admin_inventory
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # No reason: 422
        bad = await ac.delete(
            f"/api/v1/stores/{s['store_id']}/inventory/{s['inv_id']}"
        )
        assert bad.status_code == 422
        # Reason too short: 422
        short = await ac.delete(
            f"/api/v1/stores/{s['store_id']}/inventory/{s['inv_id']}",
            params={"reason": "short"},
        )
        assert short.status_code == 422
        # Reason OK
        ok = await ac.delete(
            f"/api/v1/stores/{s['store_id']}/inventory/{s['inv_id']}",
            params={"reason": "duplicate listing per support"},
        )
        assert ok.status_code == 200

    rows = list((await session.exec(select(AdminActionLog))).all())
    assert len(rows) == 1
    assert rows[0].action == "inventory.delete"
    assert rows[0].reason == "duplicate listing per support"


@pytest.mark.asyncio
async def test_admin_bulk_capped_at_100(
    seed_admin_inventory: dict,
    override_as_admin: None,
    session: AsyncSession,
) -> None:
    s = seed_admin_inventory
    # Build 101 items reusing the seeded product id (dedup means service still
    # processes one row, but the cap is checked BEFORE dedup so this triggers).
    items = [
        {"product_id": s["product_id"], "price": 10.0 + i, "stock": 1, "is_available": True}
        for i in range(101)
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/api/v1/stores/{s['store_id']}/inventory/bulk",
            json={"items": items},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "ROW_LIMIT"


@pytest.mark.asyncio
async def test_admin_write_blocked_for_non_approved_seller(
    seed_admin_inventory: dict,
    override_as_admin: None,
    session: AsyncSession,
) -> None:
    s = seed_admin_inventory
    # Flip seller to Pending
    profile = await session.get(SellerProfile, s["seller_profile_id"])
    profile.verification_status = VerificationStatus.Pending
    session.add(profile)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/api/v1/stores/{s['store_id']}/inventory/{s['inv_id']}",
            json={"product_id": s["product_id"], "price": 1.0, "stock": 1, "is_available": True},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "seller_not_active"


@pytest.mark.asyncio
async def test_seller_inventory_write_writes_no_audit_row(
    seed_admin_inventory: dict,
    override_as_seller: None,
    session: AsyncSession,
) -> None:
    """Guardrail: seller editing own inventory never emits an audit log row."""
    s = seed_admin_inventory
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/api/v1/stores/{s['store_id']}/inventory/{s['inv_id']}",
            json={
                "product_id": s["product_id"],
                "price": 123.0,
                "stock": 5,
                "is_available": True,
            },
        )
    assert resp.status_code == 200, resp.text

    rows = list((await session.exec(select(AdminActionLog))).all())
    assert rows == []
