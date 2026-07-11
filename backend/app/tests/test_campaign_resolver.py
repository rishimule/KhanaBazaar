# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    MasterProduct,
    Service,
    ServiceTranslation,
    Subcategory,
)
from app.models.commerce import DeliveryMode, Order, OrderStatus
from app.models.notification_campaign import NotificationAudience, NotificationCampaign
from app.models.platform_fee import ArrangementStatus, FeeArrangement, FeeModel
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from app.services.notification_campaigns import count_recipients, resolve_recipient_ids
from tests._helpers import make_address

STATE = "Maharashtra"


def _camp(audience: NotificationAudience, filters: dict) -> NotificationCampaign:
    return NotificationCampaign(
        audience=audience, filters=filters, channels=["in_app"],
        title="t", body="b", created_by_admin_id=1,
    )


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    cust_u1 = User(email="cr-c1@kb.com", role=UserRole.Customer, is_active=True)
    cust_u2 = User(email="cr-c2@kb.com", role=UserRole.Customer, is_active=True)
    sell_u1 = User(email="cr-s1@kb.com", role=UserRole.Seller, is_active=True)
    sell_u2 = User(email="cr-s2@kb.com", role=UserRole.Seller, is_active=True)
    for u in (cust_u1, cust_u2, sell_u1, sell_u2):
        session.add(u)
    await session.flush()

    # Customer A — Pune, will get one order (NOT new-onboarded)
    cust_a = CustomerProfile(user_id=cust_u1.id, first_name="A")
    session.add(cust_a)
    await session.flush()
    a_addr = Address(**make_address(pincode="411001", state=STATE, city="Pune"))
    session.add(a_addr)
    await session.flush()
    session.add(CustomerAddress(customer_profile_id=cust_a.id, address_id=a_addr.id, is_default=True))

    # Customer B — Mumbai, no orders (new-onboarded)
    cust_b = CustomerProfile(user_id=cust_u2.id, first_name="B")
    session.add(cust_b)
    await session.flush()
    b_addr = Address(**make_address(pincode="400001", state=STATE, city="Mumbai"))
    session.add(b_addr)
    await session.flush()
    session.add(CustomerAddress(customer_profile_id=cust_b.id, address_id=b_addr.id, is_default=True))

    # Seller X — approved, Pune, freebie arrangement + inventory (NOT new-onboarded)
    x_addr = Address(**make_address(pincode="411002", state=STATE, city="Pune"))
    session.add(x_addr)
    await session.flush()
    seller_x = SellerProfile(
        user_id=sell_u1.id, first_name="X", phone="+919811010001", business_name="X Shop",
        verification_status=VerificationStatus.Approved, business_address_id=x_addr.id,
    )
    session.add(seller_x)
    await session.flush()
    store_x_addr = Address(**make_address(pincode="411003", state=STATE, city="Pune"))
    session.add(store_x_addr)
    await session.flush()
    store_x = Store(name="X Shop", seller_profile_id=seller_x.id, address_id=store_x_addr.id)
    session.add(store_x)
    await session.flush()

    grocery = Service(slug="grocery")
    session.add(grocery)
    await session.flush()
    session.add(ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"))
    session.add(SellerProfileService(seller_profile_id=seller_x.id, service_id=grocery.id))
    cat = Category(service_id=grocery.id, slug="c")
    session.add(cat)
    await session.flush()
    sub = Subcategory(category_id=cat.id, slug="s")
    session.add(sub)
    await session.flush()
    prod = MasterProduct(subcategory_id=sub.id, slug="rice", base_price=50.0)
    session.add(prod)
    await session.flush()
    session.add(StoreInventory(store_id=store_x.id, product_id=prod.id, price=50.0, stock=5))
    session.add(FeeArrangement(
        store_id=store_x.id, service_id=grocery.id,
        model=FeeModel.Freebie, status=ArrangementStatus.Active,
    ))

    # Seller Y — approved, no inventory (new-onboarded seller)
    y_addr = Address(**make_address(pincode="560001", state="Karnataka", city="Bengaluru"))
    session.add(y_addr)
    await session.flush()
    seller_y = SellerProfile(
        user_id=sell_u2.id, first_name="Y", phone="+919811010002", business_name="Y Shop",
        verification_status=VerificationStatus.Approved, business_address_id=y_addr.id,
    )
    session.add(seller_y)
    await session.flush()
    store_y_addr = Address(**make_address(pincode="560002", state="Karnataka", city="Bengaluru"))
    session.add(store_y_addr)
    await session.flush()
    store_y = Store(name="Y Shop", seller_profile_id=seller_y.id, address_id=store_y_addr.id)
    session.add(store_y)
    await session.flush()

    # Customer A's order (makes A NOT new-onboarded)
    session.add(Order(
        customer_profile_id=cust_a.id, store_id=store_x.id, service_id=grocery.id,
        service_name_snapshot="Grocery", delivery_address_id=a_addr.id,
        delivery_mode=DeliveryMode.DoorDelivery, status=OrderStatus.Pending,
        subtotal=50.0, delivery_fee=0.0, tax=0.0, total=50.0,
        delivery_address_snapshot="Pune",
    ))
    await session.commit()

    yield {
        "cust_a": cust_a.id, "cust_b": cust_b.id,
        "seller_x": seller_x.id, "seller_y": seller_y.id,
    }


async def test_both_returns_all(session: AsyncSession, seed: dict[str, int]) -> None:
    cust, sell = await resolve_recipient_ids(session, _camp(NotificationAudience.Both, {}))
    assert set(cust) == {seed["cust_a"], seed["cust_b"]}
    assert set(sell) == {seed["seller_x"], seed["seller_y"]}


async def test_customer_location_city(session: AsyncSession, seed: dict[str, int]) -> None:
    camp = _camp(NotificationAudience.Customers, {"state": STATE, "cities": ["pune"]})
    cust, _ = await resolve_recipient_ids(session, camp)
    assert cust == [seed["cust_a"]]


async def test_customer_new_onboarded(session: AsyncSession, seed: dict[str, int]) -> None:
    camp = _camp(NotificationAudience.Customers, {"new_onboarded": True})
    cust, _ = await resolve_recipient_ids(session, camp)
    assert seed["cust_b"] in cust and seed["cust_a"] not in cust


async def test_seller_fee_model_freebie(session: AsyncSession, seed: dict[str, int]) -> None:
    camp = _camp(NotificationAudience.Sellers, {"seller_fee_models": ["freebie"]})
    _, sell = await resolve_recipient_ids(session, camp)
    assert sell == [seed["seller_x"]]


async def test_seller_new_onboarded_no_inventory(session: AsyncSession, seed: dict[str, int]) -> None:
    camp = _camp(NotificationAudience.Sellers, {"new_onboarded": True})
    _, sell = await resolve_recipient_ids(session, camp)
    assert seed["seller_y"] in sell and seed["seller_x"] not in sell


async def test_count_matches_resolve(session: AsyncSession, seed: dict[str, int]) -> None:
    camp = _camp(NotificationAudience.Both, {})
    c, s = await count_recipients(session, camp)
    cust, sell = await resolve_recipient_ids(session, camp)
    assert (c, s) == (len(cust), len(sell))
