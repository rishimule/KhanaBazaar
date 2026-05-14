# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Integration tests for GET /api/v1/carts/{store_id}/{service_id}/compare."""
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
from app.models.commerce import Cart, CartItem
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

mock_customer = User(id=501, email="cmp-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_other_customer = User(id=502, email="cmp-other@kb.com", role=UserRole.Customer, is_active=True)
mock_seller_a = User(id=511, email="cmp-sellerA@kb.com", role=UserRole.Seller, is_active=True)
mock_seller_b = User(id=512, email="cmp-sellerB@kb.com", role=UserRole.Seller, is_active=True)
mock_seller_c = User(id=513, email="cmp-sellerC@kb.com", role=UserRole.Seller, is_active=True)
mock_seller_d = User(id=514, email="cmp-sellerD@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    for u in (
        mock_customer, mock_other_customer,
        mock_seller_a, mock_seller_b, mock_seller_c, mock_seller_d,
    ):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer = CustomerProfile(user_id=mock_customer.id, first_name="C")
    other_customer = CustomerProfile(user_id=mock_other_customer.id, first_name="O")
    session.add_all([customer, other_customer])
    await session.flush()

    cust_addr = Address(**make_address(
        latitude=19.0080, longitude=72.8170, pincode="400018",
    ))
    session.add(cust_addr)
    await session.flush()
    customer_addr_link = CustomerAddress(
        customer_profile_id=customer.id, address_id=cust_addr.id, is_default=True,
    )
    other_customer_addr = Address(**make_address(
        latitude=19.0080, longitude=72.8170, pincode="400018",
    ))
    session.add(other_customer_addr)
    await session.flush()
    other_addr_link = CustomerAddress(
        customer_profile_id=other_customer.id,
        address_id=other_customer_addr.id,
        is_default=True,
    )
    session.add_all([customer_addr_link, other_addr_link])
    await session.flush()

    def _seller_addr(lat: float, lng: float) -> Address:
        return Address(**make_address(latitude=lat, longitude=lng, pincode="400018"))

    seller_addrs = {
        "A": _seller_addr(19.0078, 72.8175),
        "B": _seller_addr(19.0150, 72.8200),
        "C": _seller_addr(19.0200, 72.8250),
        "D": _seller_addr(19.2000, 73.0000),
    }
    for a in seller_addrs.values():
        session.add(a)
    await session.flush()

    sellers: dict[str, SellerProfile] = {}
    for key, user_id, addr in (
        ("A", mock_seller_a.id, seller_addrs["A"]),
        ("B", mock_seller_b.id, seller_addrs["B"]),
        ("C", mock_seller_c.id, seller_addrs["C"]),
        ("D", mock_seller_d.id, seller_addrs["D"]),
    ):
        sp = SellerProfile(
            user_id=user_id, first_name=key,
            phone=f"+91981100{user_id}", business_name=f"S{key}",
            bank_account_number="1", bank_ifsc="HDFC0000001",
            verification_status=VerificationStatus.Approved,
            business_address_id=addr.id,
        )
        session.add(sp)
        sellers[key] = sp
    await session.flush()

    stores: dict[str, Store] = {}
    for key, sp in sellers.items():
        store_addr = Address(**make_address(
            latitude=seller_addrs[key].latitude,
            longitude=seller_addrs[key].longitude,
            pincode="400018",
        ))
        session.add(store_addr)
        await session.flush()
        store = Store(
            name=f"Store{key}", seller_profile_id=sp.id,
            address_id=store_addr.id, delivery_radius_km=5.0,
        )
        session.add(store)
        stores[key] = store
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

    for sp in sellers.values():
        session.add(SellerProfileService(seller_profile_id=sp.id, service_id=grocery.id))
    await session.flush()

    cat = Category(service_id=grocery.id, slug="cat1")
    session.add(cat)
    await session.flush()
    session.add(CategoryTranslation(category_id=cat.id, language_code="en", name="Cat1"))
    sub = Subcategory(category_id=cat.id, slug="sub1")
    session.add(sub)
    await session.flush()
    session.add(SubcategoryTranslation(subcategory_id=sub.id, language_code="en", name="Sub1"))

    products: dict[str, MasterProduct] = {}
    for slug, name, base in (
        ("p1", "Product1", 100.0),
        ("p2", "Product2", 50.0),
        ("p3", "Product3", 200.0),
    ):
        p = MasterProduct(subcategory_id=sub.id, slug=slug, base_price=base)
        session.add(p)
        await session.flush()
        session.add(MasterProductTranslation(
            master_product_id=p.id, language_code="en", name=name, description=name,
        ))
        products[slug] = p
    await session.flush()

    def _inv(store: Store, prod: MasterProduct, price: float, stock: int = 10) -> StoreInventory:
        inv = StoreInventory(
            store_id=store.id, product_id=prod.id,
            price=price, stock=stock, is_available=True,
        )
        session.add(inv)
        return inv

    invs = {
        "A_p1": _inv(stores["A"], products["p1"], 100.0),
        "A_p2": _inv(stores["A"], products["p2"], 50.0),
        "A_p3": _inv(stores["A"], products["p3"], 200.0),
        "B_p1": _inv(stores["B"], products["p1"], 90.0),
        "B_p3": _inv(stores["B"], products["p3"], 180.0),
        "C_p1": _inv(stores["C"], products["p1"], 95.0),
        "C_p2": _inv(stores["C"], products["p2"], 40.0),
        "D_p1": _inv(stores["D"], products["p1"], 1.0),
        "D_p2": _inv(stores["D"], products["p2"], 1.0),
        "D_p3": _inv(stores["D"], products["p3"], 1.0),
    }
    await session.flush()

    cart = Cart(
        customer_profile_id=customer.id,
        store_id=stores["A"].id, service_id=grocery.id,
    )
    session.add(cart)
    await session.flush()
    session.add_all([
        CartItem(cart_id=cart.id, inventory_id=invs["A_p1"].id, quantity=1),
        CartItem(cart_id=cart.id, inventory_id=invs["A_p2"].id, quantity=2),
        CartItem(cart_id=cart.id, inventory_id=invs["A_p3"].id, quantity=1),
    ])

    # Capture ids as plain ints BEFORE commit. After commit() SQLAlchemy
    # expires instance attributes; accessing them during yield triggers
    # MissingGreenlet (matches the pattern in tests/test_carts.py).
    assert customer_addr_link.id is not None
    assert other_addr_link.id is not None
    assert grocery.id is not None
    assert pharmacy.id is not None
    assert sellers["A"].id is not None
    ids = {
        "customer_addr_id": customer_addr_link.id,
        "other_addr_id": other_addr_link.id,
        "store_a_id": stores["A"].id,
        "store_b_id": stores["B"].id,
        "store_c_id": stores["C"].id,
        "store_d_id": stores["D"].id,
        "service_id": grocery.id,
        "seller_a_profile_id": sellers["A"].id,
        "pharmacy_id": pharmacy.id,
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
async def test_happy_path_returns_two_ranked_alternatives(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    await _auth(mock_customer)
    try:
        resp = await client.get(
            f"/api/v1/carts/{seed['store_a_id']}/{seed['service_id']}/compare",
            params={"customer_address_id": seed["customer_addr_id"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = [a["id"] for a in body["alternatives"]]
        assert seed["store_b_id"] in ids
        assert seed["store_c_id"] in ids
        assert seed["store_d_id"] not in ids
        totals = [a["effective_total"] for a in body["alternatives"]]
        assert totals == sorted(totals)
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_effective_total_math(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    await _auth(mock_customer)
    try:
        resp = await client.get(
            f"/api/v1/carts/{seed['store_a_id']}/{seed['service_id']}/compare",
            params={"customer_address_id": seed["customer_addr_id"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        b = next(a for a in body["alternatives"] if a["id"] == seed["store_b_id"])
        assert b["covered_subtotal"] == 270.0
        assert b["imputed_subtotal"] == 100.0
        assert b["effective_total"] == 370.0
        c = next(a for a in body["alternatives"] if a["id"] == seed["store_c_id"])
        assert c["covered_subtotal"] == 175.0
        assert c["imputed_subtotal"] == 200.0
        assert c["effective_total"] == 375.0
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_imputed_flag_on_missing_items(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    await _auth(mock_customer)
    try:
        resp = await client.get(
            f"/api/v1/carts/{seed['store_a_id']}/{seed['service_id']}/compare",
            params={"customer_address_id": seed["customer_addr_id"]},
        )
        body = resp.json()
        b = next(a for a in body["alternatives"] if a["id"] == seed["store_b_id"])
        missing = [i for i in b["items"] if i["imputed"]]
        assert len(missing) == 1
        m = missing[0]
        assert m["inventory_id"] is None
        assert m["is_available"] is False
        assert m["stock"] == 0
        assert m["unit_price"] == 50.0
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_invalid_address_returns_400(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    await _auth(mock_customer)
    try:
        resp = await client.get(
            f"/api/v1/carts/{seed['store_a_id']}/{seed['service_id']}/compare",
            params={"customer_address_id": seed["other_addr_id"]},
        )
        assert resp.status_code in (400, 403, 404)
        assert resp.json()["detail"] == "invalid_address"
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_cart_not_found_returns_404(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    await _auth(mock_customer)
    try:
        resp = await client.get(
            f"/api/v1/carts/{seed['store_a_id']}/{seed['pharmacy_id']}/compare",
            params={"customer_address_id": seed["customer_addr_id"]},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "cart_not_found"
    finally:
        _clear_auth()


@pytest.mark.asyncio
async def test_unauth_returns_401(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    resp = await client.get(
        f"/api/v1/carts/{seed['store_a_id']}/{seed['service_id']}/compare",
        params={"customer_address_id": seed["customer_addr_id"]},
    )
    assert resp.status_code in (401, 403)
