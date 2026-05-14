# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Integration tests for POST /api/v1/carts/{store_id}/{service_id}/replace."""
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlmodel import select
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
from app.models.commerce import Cart, CartItem
from app.models.profile import (
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

mock_customer = User(id=601, email="rep-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_seller_a = User(id=611, email="rep-sellerA@kb.com", role=UserRole.Seller, is_active=True)
mock_seller_b = User(id=612, email="rep-sellerB@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    for u in (mock_customer, mock_seller_a, mock_seller_b):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer = CustomerProfile(user_id=mock_customer.id, first_name="C")
    session.add(customer)
    await session.flush()

    def _addr() -> Address:
        return Address(**make_address(latitude=19.0080, longitude=72.8170, pincode="400018"))

    sa, sb = _addr(), _addr()
    session.add_all([sa, sb])
    await session.flush()
    sp_a = SellerProfile(
        user_id=mock_seller_a.id, first_name="A", phone="+919811000111",
        business_name="SA", bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved, business_address_id=sa.id,
    )
    sp_b = SellerProfile(
        user_id=mock_seller_b.id, first_name="B", phone="+919811000112",
        business_name="SB", bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved, business_address_id=sb.id,
    )
    session.add_all([sp_a, sp_b])
    await session.flush()

    store_a_addr, store_b_addr = _addr(), _addr()
    session.add_all([store_a_addr, store_b_addr])
    await session.flush()
    store_a = Store(name="A", seller_profile_id=sp_a.id, address_id=store_a_addr.id)
    store_b = Store(name="B", seller_profile_id=sp_b.id, address_id=store_b_addr.id)
    session.add_all([store_a, store_b])
    await session.flush()

    grocery = Service(slug="grocery")
    pharmacy = Service(slug="pharmacy")
    session.add_all([grocery, pharmacy])
    await session.flush()
    session.add_all([
        ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"),
        ServiceTranslation(service_id=pharmacy.id, language_code="en", name="Pharmacy"),
    ])
    await session.flush()
    session.add_all([
        SellerProfileService(seller_profile_id=sp_a.id, service_id=grocery.id),
        SellerProfileService(seller_profile_id=sp_b.id, service_id=grocery.id),
    ])
    await session.flush()

    cat = Category(service_id=grocery.id, slug="cat1")
    session.add(cat)
    await session.flush()
    session.add(CategoryTranslation(category_id=cat.id, language_code="en", name="C"))
    sub = Subcategory(category_id=cat.id, slug="sub1")
    session.add(sub)
    await session.flush()
    session.add(SubcategoryTranslation(subcategory_id=sub.id, language_code="en", name="S"))

    p1 = MasterProduct(subcategory_id=sub.id, slug="p1", base_price=100.0)
    p2 = MasterProduct(subcategory_id=sub.id, slug="p2", base_price=50.0)
    session.add_all([p1, p2])
    await session.flush()
    session.add_all([
        MasterProductTranslation(master_product_id=p1.id, language_code="en", name="P1", description="P1"),
        MasterProductTranslation(master_product_id=p2.id, language_code="en", name="P2", description="P2"),
    ])
    await session.flush()

    inv_a_p1 = StoreInventory(store_id=store_a.id, product_id=p1.id, price=100.0, stock=10, is_available=True)
    inv_a_p2 = StoreInventory(store_id=store_a.id, product_id=p2.id, price=50.0, stock=10, is_available=True)
    inv_b_p1 = StoreInventory(store_id=store_b.id, product_id=p1.id, price=90.0, stock=3, is_available=True)
    inv_b_p2 = StoreInventory(store_id=store_b.id, product_id=p2.id, price=40.0, stock=10, is_available=True)
    session.add_all([inv_a_p1, inv_a_p2, inv_b_p1, inv_b_p2])
    await session.flush()

    cart_a = Cart(customer_profile_id=customer.id, store_id=store_a.id, service_id=grocery.id)
    session.add(cart_a)
    await session.flush()
    session.add_all([
        CartItem(cart_id=cart_a.id, inventory_id=inv_a_p1.id, quantity=1),
        CartItem(cart_id=cart_a.id, inventory_id=inv_a_p2.id, quantity=1),
    ])

    assert customer.id is not None
    assert store_a.id is not None
    assert store_b.id is not None
    assert grocery.id is not None
    assert pharmacy.id is not None
    assert inv_a_p1.id is not None
    assert inv_a_p2.id is not None
    assert inv_b_p1.id is not None
    assert inv_b_p2.id is not None
    assert cart_a.id is not None
    ids = {
        "customer_profile_id": customer.id,
        "store_a_id": store_a.id,
        "store_b_id": store_b.id,
        "service_id": grocery.id,
        "pharmacy_id": pharmacy.id,
        "inv_a_p1": inv_a_p1.id,
        "inv_a_p2": inv_a_p2.id,
        "inv_b_p1": inv_b_p1.id,
        "inv_b_p2": inv_b_p2.id,
        "cart_a_id": cart_a.id,
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
async def test_happy_path_replaces_empty_b_cart(
    client: AsyncClient, seed: dict[str, int], session: AsyncSession,
) -> None:
    await _auth(mock_customer)
    try:
        resp = await client.post(
            f"/api/v1/carts/{seed['store_b_id']}/{seed['service_id']}/replace",
            json={"items": [
                {"inventory_id": seed["inv_b_p1"], "quantity": 1},
                {"inventory_id": seed["inv_b_p2"], "quantity": 1},
            ]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["adjustments"] == []
        items_a = (await session.exec(
            select(CartItem).where(CartItem.cart_id == seed["cart_a_id"])
        )).all()
        assert len(items_a) == 2
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_pre_existing_b_cart_replaced(
    client: AsyncClient, seed: dict[str, int], session: AsyncSession,
) -> None:
    cart_b = Cart(
        customer_profile_id=seed["customer_profile_id"],
        store_id=seed["store_b_id"],
        service_id=seed["service_id"],
    )
    session.add(cart_b)
    await session.flush()
    session.add(CartItem(cart_id=cart_b.id, inventory_id=seed["inv_b_p1"], quantity=5))
    cart_b_id = cart_b.id
    await session.commit()

    await _auth(mock_customer)
    try:
        resp = await client.post(
            f"/api/v1/carts/{seed['store_b_id']}/{seed['service_id']}/replace",
            json={"items": [{"inventory_id": seed["inv_b_p2"], "quantity": 1}]},
        )
        assert resp.status_code == 200
        items = (await session.exec(
            select(CartItem).where(CartItem.cart_id == cart_b_id)
        )).all()
        assert len(items) == 1
        assert items[0].inventory_id == seed["inv_b_p2"]
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_stock_capped_adjustment(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    await _auth(mock_customer)
    try:
        resp = await client.post(
            f"/api/v1/carts/{seed['store_b_id']}/{seed['service_id']}/replace",
            json={"items": [{"inventory_id": seed["inv_b_p1"], "quantity": 5}]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["adjustments"]) == 1
        adj = body["adjustments"][0]
        assert adj["reason"] == "stock_capped"
        assert adj["requested_quantity"] == 5
        assert adj["granted_quantity"] == 3
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_stock_exhausted_adjustment(
    client: AsyncClient, seed: dict[str, int], session: AsyncSession,
) -> None:
    inv = await session.get(StoreInventory, seed["inv_b_p1"])
    assert inv is not None
    inv.stock = 0
    await session.commit()

    await _auth(mock_customer)
    try:
        resp = await client.post(
            f"/api/v1/carts/{seed['store_b_id']}/{seed['service_id']}/replace",
            json={"items": [
                {"inventory_id": seed["inv_b_p1"], "quantity": 1},
                {"inventory_id": seed["inv_b_p2"], "quantity": 1},
            ]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        adjustments = body["adjustments"]
        assert any(
            a["reason"] == "stock_exhausted" and a["inventory_id"] == seed["inv_b_p1"]
            for a in adjustments
        )
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_item_unavailable_adjustment(
    client: AsyncClient, seed: dict[str, int], session: AsyncSession,
) -> None:
    inv = await session.get(StoreInventory, seed["inv_b_p1"])
    assert inv is not None
    inv.is_available = False
    await session.commit()

    await _auth(mock_customer)
    try:
        resp = await client.post(
            f"/api/v1/carts/{seed['store_b_id']}/{seed['service_id']}/replace",
            json={"items": [
                {"inventory_id": seed["inv_b_p1"], "quantity": 1},
                {"inventory_id": seed["inv_b_p2"], "quantity": 1},
            ]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert any(
            a["reason"] == "item_unavailable" and a["inventory_id"] == seed["inv_b_p1"]
            for a in body["adjustments"]
        )
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_empty_items_when_all_drop(
    client: AsyncClient, seed: dict[str, int], session: AsyncSession,
) -> None:
    inv1 = await session.get(StoreInventory, seed["inv_b_p1"])
    inv2 = await session.get(StoreInventory, seed["inv_b_p2"])
    assert inv1 is not None and inv2 is not None
    inv1.is_available = False
    inv2.stock = 0
    await session.commit()

    await _auth(mock_customer)
    try:
        resp = await client.post(
            f"/api/v1/carts/{seed['store_b_id']}/{seed['service_id']}/replace",
            json={"items": [
                {"inventory_id": seed["inv_b_p1"], "quantity": 1},
                {"inventory_id": seed["inv_b_p2"], "quantity": 1},
            ]},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "empty_items"
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_inventory_store_mismatch(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    await _auth(mock_customer)
    try:
        resp = await client.post(
            f"/api/v1/carts/{seed['store_b_id']}/{seed['service_id']}/replace",
            json={"items": [{"inventory_id": seed["inv_a_p1"], "quantity": 1}]},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "inventory_store_mismatch"
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_inventory_not_found(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    await _auth(mock_customer)
    try:
        resp = await client.post(
            f"/api/v1/carts/{seed['store_b_id']}/{seed['service_id']}/replace",
            json={"items": [{"inventory_id": 9999999, "quantity": 1}]},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "inventory_not_found"
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_source_a_cart_preserved(
    client: AsyncClient, seed: dict[str, int], session: AsyncSession,
) -> None:
    await _auth(mock_customer)
    try:
        await client.post(
            f"/api/v1/carts/{seed['store_b_id']}/{seed['service_id']}/replace",
            json={"items": [{"inventory_id": seed["inv_b_p1"], "quantity": 1}]},
        )
        items_a = (await session.exec(
            select(CartItem).where(CartItem.cart_id == seed["cart_a_id"])
        )).all()
        assert len(items_a) == 2
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_idempotent_retry(
    client: AsyncClient, seed: dict[str, int], session: AsyncSession,
) -> None:
    await _auth(mock_customer)
    try:
        for _ in range(2):
            resp = await client.post(
                f"/api/v1/carts/{seed['store_b_id']}/{seed['service_id']}/replace",
                json={"items": [{"inventory_id": seed["inv_b_p1"], "quantity": 1}]},
            )
            assert resp.status_code == 200, resp.text
        b_cart = (await session.exec(
            select(Cart).where(
                Cart.customer_profile_id == seed["customer_profile_id"],
                Cart.store_id == seed["store_b_id"],
                Cart.service_id == seed["service_id"],
            )
        )).first()
        assert b_cart is not None
        items = (await session.exec(
            select(CartItem).where(CartItem.cart_id == b_cart.id)
        )).all()
        assert len(items) == 1
        assert items[0].quantity == 1
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_unauth_returns_401(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    resp = await client.post(
        f"/api/v1/carts/{seed['store_b_id']}/{seed['service_id']}/replace",
        json={"items": [{"inventory_id": seed["inv_b_p1"], "quantity": 1}]},
    )
    assert resp.status_code in (401, 403)
