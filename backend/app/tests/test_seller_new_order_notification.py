# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.address import Address
from app.models.base import AccountStatus, User, UserRole
from app.models.commerce import Cart, CartItem
from app.models.notification import Notification, NotificationType
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from app.services.notifications import record_seller_notification
from tests._helpers import make_address

_CUSTOMER = User(id=9110, email="snoa-cust@kb.com", role=UserRole.Customer, is_active=True)
_SELLER = User(id=9111, email="snoa-store@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture
async def order_seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    """One customer with an address + a cart holding one in-stock item, and one
    approved seller owning a store that sells the cart's service.

    Mirrors the `seed` fixture in tests/test_orders.py, trimmed to a single
    store, and overrides get_current_user to the customer for the whole test.
    """
    for u in (_CUSTOMER, _SELLER):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer_profile = CustomerProfile(user_id=_CUSTOMER.id, first_name="Cust")
    session.add(customer_profile)
    await session.flush()

    cust_addr = Address(**make_address(pincode="560050"))
    seller_business_addr = Address(**make_address(pincode="560100"))
    store_addr = Address(**make_address(pincode="560110"))
    session.add_all([cust_addr, seller_business_addr, store_addr])
    await session.flush()

    cust_address = CustomerAddress(
        customer_profile_id=customer_profile.id,
        address_id=cust_addr.id,
        is_default=True,
    )
    session.add(cust_address)

    seller_profile = SellerProfile(
        user_id=_SELLER.id,
        first_name="S1",
        phone="+919800009110",
        business_name="S1 Store",
        bank_account_number="1",
        bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_business_addr.id,
    )
    session.add(seller_profile)
    await session.flush()

    store = Store(
        name="Store A",
        seller_profile_id=seller_profile.id,
        address_id=store_addr.id,
    )
    session.add(store)
    await session.flush()

    from tests.test_carts import _seed_product

    product, grocery_service_id = await _seed_product(
        session,
        service_slug="grocery",
        category_slug="food",
        subcategory_slug="fruit",
        product_slug="apple",
        name="Apple",
        base_price=50.0,
    )
    session.add(
        SellerProfileService(
            seller_profile_id=seller_profile.id, service_id=grocery_service_id
        )
    )
    await session.flush()

    inv = StoreInventory(store_id=store.id, product_id=product.id, price=50.0, stock=10)
    session.add(inv)
    await session.flush()

    cart = Cart(
        customer_profile_id=customer_profile.id,
        store_id=store.id,
        service_id=grocery_service_id,
    )
    session.add(cart)
    await session.flush()
    session.add(CartItem(cart_id=cart.id, inventory_id=inv.id, quantity=2))

    assert store.id is not None
    assert cust_address.id is not None
    assert seller_profile.id is not None
    assert _SELLER.id is not None
    assert customer_profile.id is not None
    ids: dict[str, int] = {
        "store_id": store.id,
        "service_id": grocery_service_id,
        "address_id": cust_address.id,
        "seller_profile_id": seller_profile.id,
        "seller_user_id": _SELLER.id,
        "customer_profile_id": customer_profile.id,
    }
    await session.commit()

    app.dependency_overrides[get_current_user] = lambda: _CUSTOMER
    try:
        yield ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_seller_new_order_member_exists() -> None:
    assert NotificationType.SellerNewOrder.value == "seller_new_order"


@pytest.mark.asyncio
async def test_record_seller_notification_persists_order_id(
    session: AsyncSession,
) -> None:
    user = User(id=9101, email="snoa-seller@kb.com", role=UserRole.Seller, is_active=True)
    session.add(user)
    biz_addr = Address(**make_address(pincode="560077"))
    session.add(biz_addr)
    await session.flush()
    profile = SellerProfile(
        user_id=user.id,
        first_name="Snoa",
        business_name="Test Store",
        phone="+919876500011",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz_addr.id,
    )
    session.add(profile)
    await session.flush()
    assert profile.id is not None

    await record_seller_notification(
        session,
        seller_profile_id=profile.id,
        type=NotificationType.SellerNewOrder,
        title="New order #1",
        body="1 item.",
        status_value="new_order",
        order_id=None,
    )
    await session.commit()

    row = (
        await session.exec(
            select(Notification).where(Notification.seller_profile_id == profile.id)
        )
    ).one()
    assert row.type == NotificationType.SellerNewOrder
    assert row.status_value == "new_order"
    assert row.order_id is None


async def _place_order(seed: dict[str, int]) -> Response:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/api/v1/orders",
            json={
                "store_id": seed["store_id"],
                "service_id": seed["service_id"],
                "payment_method": "cash",
                "customer_address_id": seed["address_id"],
            },
        )


@pytest.mark.asyncio
async def test_place_order_writes_seller_notification(
    session: AsyncSession, order_seed: dict[str, int]
) -> None:
    """Placing an order writes exactly one SellerNewOrder row for the store owner."""
    res = await _place_order(order_seed)
    assert res.status_code == 201, res.text
    order_id = res.json()["id"]

    rows = (
        await session.exec(
            select(Notification)
            .where(Notification.seller_profile_id == order_seed["seller_profile_id"])
            .where(Notification.type == NotificationType.SellerNewOrder)
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].order_id == order_id
    assert rows[0].status_value == "new_order"
    assert f"#{order_id}" in rows[0].title

    # The seller row's extra mid-request commit must not swallow the customer's
    # own order-placed notification.
    customer_rows = (
        await session.exec(
            select(Notification)
            .where(
                Notification.customer_profile_id == order_seed["customer_profile_id"]
            )
            .where(Notification.type == NotificationType.OrderStatus)
        )
    ).all()
    assert [r.order_id for r in customer_rows] == [order_id]


@pytest.mark.asyncio
async def test_no_seller_notification_for_inactive_seller_account(
    session: AsyncSession, order_seed: dict[str, int]
) -> None:
    seller_user = (
        await session.exec(select(User).where(User.id == order_seed["seller_user_id"]))
    ).one()
    seller_user.account_status = AccountStatus.deactivated
    session.add(seller_user)
    await session.commit()

    res = await _place_order(order_seed)
    assert res.status_code == 201, res.text

    rows = (
        await session.exec(
            select(Notification).where(
                Notification.type == NotificationType.SellerNewOrder
            )
        )
    ).all()
    assert rows == []


@pytest.mark.asyncio
async def test_place_order_survives_seller_notification_failure(
    order_seed: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A notification blow-up must not 500 the checkout path."""

    async def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("notification exploded")

    monkeypatch.setattr(
        "app.services.seller_order_notifications.record_seller_notification", _boom
    )
    res = await _place_order(order_seed)
    assert res.status_code == 201, res.text
