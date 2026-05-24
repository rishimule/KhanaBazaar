# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Integration tests for POST /api/v1/orders/{order_id}/reorder."""
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    CategoryTranslation,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.commerce import Order, OrderItem, OrderStatus
from app.models.profile import (
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

mock_customer = User(id=701, email="reo-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_other = User(id=702, email="reo-other@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=711, email="reo-seller@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    for u in (mock_customer, mock_other, mock_seller):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer = CustomerProfile(user_id=mock_customer.id, first_name="C")
    other = CustomerProfile(user_id=mock_other.id, first_name="O")
    session.add_all([customer, other])
    await session.flush()

    def _addr() -> Address:
        return Address(**make_address(latitude=19.0080, longitude=72.8170, pincode="400018"))

    sp_addr, store_addr, deliv_addr = _addr(), _addr(), _addr()
    session.add_all([sp_addr, store_addr, deliv_addr])
    await session.flush()

    sp = SellerProfile(
        user_id=mock_seller.id, first_name="S", phone="+919811000700",
        business_name="S", bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved, business_address_id=sp_addr.id,
    )
    session.add(sp)
    await session.flush()

    store = Store(name="ReoStore", seller_profile_id=sp.id, address_id=store_addr.id)
    session.add(store)
    await session.flush()

    grocery = Service(slug="grocery")
    session.add(grocery)
    await session.flush()
    session.add(ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"))
    session.add(SellerProfileService(seller_profile_id=sp.id, service_id=grocery.id))
    await session.flush()

    cat = Category(service_id=grocery.id, slug="cat1")
    session.add(cat)
    await session.flush()
    session.add(CategoryTranslation(category_id=cat.id, language_code="en", name="C"))
    sub = Subcategory(category_id=cat.id, slug="sub1")
    session.add(sub)
    await session.flush()
    session.add(SubcategoryTranslation(subcategory_id=sub.id, language_code="en", name="S"))

    p1 = MasterProduct(subcategory_id=sub.id, slug="p1", base_price=100.0, image_url="http://img/p1")
    p2 = MasterProduct(subcategory_id=sub.id, slug="p2", base_price=50.0)
    session.add_all([p1, p2])
    await session.flush()
    session.add_all([
        MasterProductTranslation(master_product_id=p1.id, language_code="en", name="P1", description="d"),
        MasterProductTranslation(master_product_id=p2.id, language_code="en", name="P2", description="d"),
    ])
    await session.flush()

    inv1 = StoreInventory(store_id=store.id, product_id=p1.id, price=110.0, stock=10, is_available=True)
    inv2 = StoreInventory(store_id=store.id, product_id=p2.id, price=55.0, stock=10, is_available=True)
    session.add_all([inv1, inv2])
    await session.flush()

    order = Order(
        customer_profile_id=customer.id, store_id=store.id, service_id=grocery.id,
        service_name_snapshot="Grocery", delivery_address_id=deliv_addr.id,
        status=OrderStatus.Delivered, subtotal=205.0, delivery_fee=0.0, tax=0.0, total=205.0,
        delivery_address_snapshot="addr",
    )
    session.add(order)
    await session.flush()
    session.add_all([
        OrderItem(order_id=order.id, inventory_id=inv1.id, product_name_snapshot="P1",
                  unit_price_snapshot=100.0, quantity=2, line_total=200.0),
        OrderItem(order_id=order.id, inventory_id=inv2.id, product_name_snapshot="P2",
                  unit_price_snapshot=50.0, quantity=1, line_total=50.0),
    ])

    assert order.id is not None
    ids = {
        "order_id": order.id, "store_id": store.id, "service_id": grocery.id,
        "inv1": inv1.id, "inv2": inv2.id, "p1": p1.id, "p2": p2.id,
    }
    await session.commit()
    yield ids


async def _auth(user: User) -> None:
    async def override() -> User:
        return user
    app.dependency_overrides[get_current_user] = override


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_happy_path_resolves_all_items(client: AsyncClient, seed: dict[str, int]) -> None:
    await _auth(mock_customer)
    try:
        resp = await client.post(f"/api/v1/orders/{seed['order_id']}/reorder")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["store_id"] == seed["store_id"]
        assert body["service_id"] == seed["service_id"]
        assert body["adjustments"] == []
        items = {i["inventory_id"]: i for i in body["items"]}
        assert items[seed["inv1"]]["unit_price"] == 110.0  # current price, not snapshot
        assert items[seed["inv1"]]["quantity"] == 2
        assert items[seed["inv1"]]["product_name"] == "P1"
        assert items[seed["inv1"]]["image_url"] == "http://img/p1"
        assert items[seed["inv2"]]["quantity"] == 1
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_stock_capped(client: AsyncClient, seed: dict[str, int], session: AsyncSession) -> None:
    inv = await session.get(StoreInventory, seed["inv1"])
    assert inv is not None
    inv.stock = 1  # order asked for 2
    session.add(inv)
    await session.commit()

    await _auth(mock_customer)
    try:
        resp = await client.post(f"/api/v1/orders/{seed['order_id']}/reorder")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        line = next(i for i in body["items"] if i["inventory_id"] == seed["inv1"])
        assert line["quantity"] == 1  # capped, still added
        adj = next(a for a in body["adjustments"] if a["inventory_id"] == seed["inv1"])
        assert adj["reason"] == "stock_capped"
        assert adj["granted_quantity"] == 1
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_stock_exhausted(client: AsyncClient, seed: dict[str, int], session: AsyncSession) -> None:
    inv = await session.get(StoreInventory, seed["inv1"])
    assert inv is not None
    inv.stock = 0
    session.add(inv)
    await session.commit()

    await _auth(mock_customer)
    try:
        resp = await client.post(f"/api/v1/orders/{seed['order_id']}/reorder")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert all(i["inventory_id"] != seed["inv1"] for i in body["items"])
        adj = next(a for a in body["adjustments"] if a["inventory_id"] == seed["inv1"])
        assert adj["reason"] == "stock_exhausted"
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_item_unavailable_when_flag_off(client: AsyncClient, seed: dict[str, int], session: AsyncSession) -> None:
    inv = await session.get(StoreInventory, seed["inv1"])
    assert inv is not None
    inv.is_available = False
    session.add(inv)
    await session.commit()

    await _auth(mock_customer)
    try:
        resp = await client.post(f"/api/v1/orders/{seed['order_id']}/reorder")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert all(i["inventory_id"] != seed["inv1"] for i in body["items"])
        adj = next(a for a in body["adjustments"] if a["inventory_id"] == seed["inv1"])
        assert adj["reason"] == "item_unavailable"
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_null_inventory_is_unavailable(client: AsyncClient, seed: dict[str, int], session: AsyncSession) -> None:
    # A StoreInventory row referenced by an OrderItem cannot be deleted (FK
    # orderitem_inventory_id_fkey). The real "dangling" case is an OrderItem
    # with a NULL inventory_id, which must resolve to item_unavailable.
    session.add(OrderItem(
        order_id=seed["order_id"], inventory_id=None, product_name_snapshot="Gone",
        unit_price_snapshot=10.0, quantity=1, line_total=10.0,
    ))
    await session.commit()

    await _auth(mock_customer)
    try:
        resp = await client.post(f"/api/v1/orders/{seed['order_id']}/reorder")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # The two real items still resolve; the null-inventory line is dropped.
        assert len(body["items"]) == 2
        adj = next(a for a in body["adjustments"] if a["reason"] == "item_unavailable")
        assert adj["granted_quantity"] == 0
    finally:
        _clear_auth()
