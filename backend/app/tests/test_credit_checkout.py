# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import uuid

import pytest
from fastapi import HTTPException
from sqlmodel import select

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.commerce import Cart, CartItem, Payment, PaymentMethod, PaymentStatus
from app.models.credit import (
    CreditAccount,
    CreditAccountStatus,
    CreditEntryType,
    CreditLedgerEntry,
    SellerCreditConfig,
)
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from app.services.checkout import place_order_for_sub_basket
from tests._helpers import make_address


async def _seed(session, *, credit_limit=2000.0, outstanding=0.0,
                enabled=True, status=CreditAccountStatus.active, make_account=True):
    from tests.test_carts import _seed_product

    cu = User(email=f"c-{uuid.uuid4().hex[:8]}@x.test", role=UserRole.Customer)
    su = User(email=f"s-{uuid.uuid4().hex[:8]}@x.test", role=UserRole.Seller)
    session.add_all([cu, su])
    await session.flush()
    cprof = CustomerProfile(user_id=cu.id, first_name="C")
    caddr = Address(**make_address())
    session.add_all([cprof, caddr])
    await session.flush()
    session.add(CustomerAddress(customer_profile_id=cprof.id, address_id=caddr.id, is_default=True))
    saddr = Address(**make_address())
    session.add(saddr)
    await session.flush()
    sprof = SellerProfile(user_id=su.id, first_name="S", phone=f"+9198{uuid.uuid4().int % 10**8:08d}",
                          business_name="S Store", verification_status=VerificationStatus.Approved,
                          business_address_id=saddr.id)
    session.add(sprof)
    await session.flush()
    product, service_id = await _seed_product(
        session, service_slug=f"svc-{uuid.uuid4().hex[:6]}", category_slug=f"cat-{uuid.uuid4().hex[:6]}",
        subcategory_slug=f"sub-{uuid.uuid4().hex[:6]}", product_slug=f"p-{uuid.uuid4().hex[:6]}",
        name="Apple", base_price=50.0,
    )
    session.add(SellerProfileService(seller_profile_id=sprof.id, service_id=service_id))
    store_addr = Address(**make_address())
    session.add(store_addr)
    await session.flush()
    store = Store(name="S Store", seller_profile_id=sprof.id, address_id=store_addr.id)
    session.add(store)
    await session.flush()
    inv = StoreInventory(store_id=store.id, product_id=product.id, price=50.0, stock=10)
    session.add(inv)
    await session.flush()
    cart = Cart(customer_profile_id=cprof.id, store_id=store.id, service_id=service_id)
    session.add(cart)
    await session.flush()
    session.add(CartItem(cart_id=cart.id, inventory_id=inv.id, quantity=2))  # total = 100

    session.add(SellerCreditConfig(seller_profile_id=sprof.id, credit_enabled=enabled,
                                   max_limit_per_customer=10000))
    if make_account:
        session.add(CreditAccount(seller_profile_id=sprof.id, customer_profile_id=cprof.id,
                                  credit_limit=credit_limit, outstanding_balance=outstanding,
                                  status=status, granted_by_user_id=su.id))
    await session.commit()
    return {"user": cu, "seller_user": su, "address_id": caddr.id, "store_id": store.id,
            "service_id": service_id, "seller_profile_id": sprof.id,
            "customer_profile_id": cprof.id}


@pytest.mark.asyncio
async def test_credit_checkout_charges_account(session):
    s = await _seed(session, credit_limit=2000.0)
    order = await place_order_for_sub_basket(
        session, s["user"], customer_address_id=s["address_id"], store_id=s["store_id"], service_id=s["service_id"], payment_method=PaymentMethod.Credit
    )
    assert order.total == 100.0
    payment = (await session.exec(select(Payment).where(Payment.order_id == order.id))).one()
    assert payment.method == PaymentMethod.Credit
    assert payment.status == PaymentStatus.Pending
    acct = (await session.exec(select(CreditAccount).where(
        CreditAccount.seller_profile_id == s["seller_profile_id"]))).one()
    assert acct.outstanding_balance == 100.0
    entry = (await session.exec(select(CreditLedgerEntry).where(
        CreditLedgerEntry.credit_account_id == acct.id))).one()
    assert entry.entry_type == CreditEntryType.charge
    assert entry.order_id == order.id


@pytest.mark.asyncio
async def test_credit_checkout_insufficient_blocks(session):
    s = await _seed(session, credit_limit=50.0)  # total 100 > 50
    with pytest.raises(HTTPException) as exc:
        await place_order_for_sub_basket(
            session, s["user"], customer_address_id=s["address_id"], store_id=s["store_id"], service_id=s["service_id"], payment_method=PaymentMethod.Credit
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "insufficient_credit"
    # no order/charge landed
    assert (await session.exec(select(CreditLedgerEntry))).first() is None


@pytest.mark.asyncio
async def test_credit_checkout_suspended_blocked(session):
    s = await _seed(session, credit_limit=2000.0, status=CreditAccountStatus.suspended)
    with pytest.raises(HTTPException) as exc:
        await place_order_for_sub_basket(
            session, s["user"], customer_address_id=s["address_id"], store_id=s["store_id"], service_id=s["service_id"], payment_method=PaymentMethod.Credit
        )
    assert exc.value.detail["error"] == "credit_not_available"


@pytest.mark.asyncio
async def test_credit_checkout_no_account_blocked(session):
    s = await _seed(session, make_account=False)
    with pytest.raises(HTTPException) as exc:
        await place_order_for_sub_basket(
            session, s["user"], customer_address_id=s["address_id"], store_id=s["store_id"], service_id=s["service_id"], payment_method=PaymentMethod.Credit
        )
    assert exc.value.detail["error"] == "credit_not_available"


@pytest.mark.asyncio
async def test_credit_checkout_disabled_blocked(session):
    s = await _seed(session, credit_limit=2000.0, enabled=False)
    with pytest.raises(HTTPException) as exc:
        await place_order_for_sub_basket(
            session, s["user"], customer_address_id=s["address_id"], store_id=s["store_id"], service_id=s["service_id"], payment_method=PaymentMethod.Credit
        )
    assert exc.value.detail["error"] == "credit_not_available"
