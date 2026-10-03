# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.commerce import Order
from app.models.courier import OrderCourier
from app.models.profile import CustomerAddress, SellerProfile
from app.models.store import Store, StoreInventory
from tests._courier_helpers import (
    CUSTOMER,
    CourierWorld,
    client_as,
    place_courier_order,
    seed_courier_world,
)


def _body(world: CourierWorld, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "customer_address_id": world.courier_address_id,
        "store_id": world.store_id,
        "service_id": world.service_id,
        "payment_method": "upi",
        "delivery_mode": "courier",
        "recipient_name": "Asha Rao",
        "recipient_phone": "+919900000001",
    }
    body.update(overrides)
    return {k: v for k, v in body.items() if v is not None}


async def _post(world: CourierWorld, **overrides: Any):
    async with client_as(CUSTOMER) as ac:
        return await ac.post("/api/v1/orders", json=_body(world, **overrides))


async def test_courier_order_is_created_pending_with_no_fee(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    assert order["delivery_mode"] == "courier"
    assert order["status"] == "pending"
    assert order["delivery_fee"] == 0.0
    assert order["total"] == 200.0  # 2 × ₹100, nothing for the courier yet
    assert order["payment"] == {
        **order["payment"], "method": "upi", "status": "pending", "amount": 200.0,
    }
    row = (await session.exec(select(OrderCourier).where(OrderCourier.order_id == order["id"]))).one()
    assert (row.recipient_name, row.recipient_phone, row.apply_store_credit) == (
        "Asha Rao", "+919900000001", True,
    )
    inv = await session.get(StoreInventory, world.inventory_id)
    assert inv is not None
    await session.refresh(inv)
    assert inv.stock == 8  # reserved at placement


async def test_recipient_phone_is_normalized(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world, recipient_phone="+91 99000-00001")
    row = (await session.exec(select(OrderCourier).where(OrderCourier.order_id == order["id"]))).one()
    assert row.recipient_phone == "+919900000001"


async def test_bank_transfer_is_allowed_cash_and_credit_are_not(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    cash = await _post(world, payment_method="cash")
    credit = await _post(world, payment_method="credit")
    assert cash.status_code == 422 and cash.json()["detail"] == "payment_method_not_allowed"
    assert credit.status_code == 422 and credit.json()["detail"] == "payment_method_not_allowed"
    order = await place_courier_order(world, payment_method="net_banking")
    assert order["payment"]["method"] == "net_banking"


async def test_courier_fields_are_strict(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    door_with_recipient = await _post(world, delivery_mode="door_delivery", customer_address_id=world.local_address_id)
    window = await _post(world, preferred_delivery_date="2099-01-01", preferred_delivery_window="morning")
    no_name = await _post(world, recipient_name="   ")
    bad_phone = await _post(world, recipient_phone="12345")
    assert door_with_recipient.status_code == 422
    assert door_with_recipient.json()["detail"] == "courier_fields_not_allowed"
    assert window.status_code == 422
    assert no_name.json()["detail"] == "recipient_name_required"
    assert bad_phone.json()["detail"] == "invalid_recipient_phone"


async def test_preferred_window_is_rejected_for_courier(session: AsyncSession) -> None:
    from app.utils.delivery_window import ist_today

    world = await seed_courier_world(session)
    resp = await _post(
        world, preferred_delivery_date=ist_today().isoformat(), preferred_delivery_window="evening",
    )
    assert resp.status_code == 422 and resp.json()["detail"] == "preferred_window_not_allowed"


async def test_courier_must_be_switched_on(session: AsyncSession) -> None:
    world = await seed_courier_world(session, courier_enabled=False)
    resp = await _post(world)
    assert resp.status_code == 409 and resp.json()["detail"]["detail"] == "courier_unavailable"


async def test_chosen_payee_must_be_live(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    seller.bank_transfer_enabled = False
    await session.commit()
    resp = await _post(world, payment_method="net_banking")
    assert resp.status_code == 409 and resp.json()["detail"] == "bank_transfer_unavailable"


async def test_zone_must_be_the_courier_ring(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    local = await _post(world, customer_address_id=world.local_address_id)
    far = await _post(world, customer_address_id=world.far_address_id)
    assert local.status_code == 422 and local.json()["detail"] == "address_within_local_area"
    assert far.status_code == 422 and far.json()["detail"] == "outside_courier_area"


async def test_destination_must_be_in_india_with_a_pin(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    link = await session.get(CustomerAddress, world.courier_address_id)
    assert link is not None
    address = await session.get(Address, link.address_id)
    assert address is not None
    address.country = "Nepal"
    await session.commit()
    resp = await _post(world)
    assert resp.status_code == 422 and resp.json()["detail"] == "courier_destination_unsupported"


async def test_paused_store_still_blocks_a_courier_checkout(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    store = await session.get(Store, world.store_id)
    assert store is not None
    store.is_paused = True
    await session.commit()
    resp = await _post(world)
    assert resp.status_code == 409 and resp.json()["detail"]["detail"] == "store_paused"


async def test_door_delivery_is_unchanged(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    resp = await _post(
        world, delivery_mode="door_delivery", customer_address_id=world.local_address_id,
        recipient_name=None, recipient_phone=None,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["delivery_fee"] == 30.0  # under the ₹500 threshold
    rows = (await session.exec(select(OrderCourier))).all()
    assert rows == []


async def test_store_credit_applies_to_the_goods(session: AsyncSession) -> None:
    from app.models.returns import StoreCreditEntryType
    from app.services import customer_store_credit as store_credit

    world = await seed_courier_world(session)
    account = await store_credit.get_or_create_account(
        session, seller_profile_id=world.seller_profile_id,
        customer_profile_id=world.customer_profile_id, for_update=True,
    )
    await store_credit.grant(
        session, account, 50.0, entry_type=StoreCreditEntryType.admin_adjust, note="test",
    )
    await session.commit()
    order = await place_courier_order(world)
    assert order["store_credit_applied"] == 50.0
    assert order["payment"]["amount"] == 150.0
    saved = await session.get(Order, order["id"])
    assert saved is not None
