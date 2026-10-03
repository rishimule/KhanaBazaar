# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import timedelta

import httpx
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import DeliveryMode, Order, OrderStatus
from app.models.profile import CustomerAddress, SellerProfileService
from app.services import returns as returns_svc
from app.services.fee_order_value import compute_order_value_sales
from app.utils.delivery_window import ist_today
from tests._courier_helpers import (
    ADMIN,
    CUSTOMER,
    SELLER,
    client_as,
    get_order,
    insert_courier_order,
    order_at_dispatched,
    order_at_paid,
    place_courier_order,
    seed_courier_world,
)


async def _rewind(order_id: int, to_status: str) -> httpx.Response:
    async with client_as(ADMIN) as ac:
        return await ac.post(f"/api/v1/admin/orders/{order_id}/rewind", json={
            "to_status": to_status, "reason": "Corrected by support after a call",
        })


async def test_rewind_paid_to_accepted_reopens_payment(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_paid(world)
    resp = await _rewind(order["id"], "accepted")
    assert resp.status_code == 200 and resp.json() == {"status": "accepted"}
    view = await get_order(order["id"])
    assert view["payment"]["status"] == "pending" and view["payment"]["paid_at"] is None
    assert view["courier"]["eta_from"] is None and view["courier"]["eta_to"] is None


async def test_rewind_a_shipped_order_clears_tracking(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world, tracking_number="T1", tracking_url="https://t.example/1")
    assert (await _rewind(order["id"], "packed")).status_code == 200
    view = await get_order(order["id"], as_user=SELLER)
    assert view["status"] == "packed"
    assert view["courier"]["tracking_number"] is None and view["courier"]["tracking_url"] is None
    assert view["delivery"]["dispatched_at"] is None
    assert (await _rewind(order["id"], "paid")).status_code == 200
    view = await get_order(order["id"], as_user=SELLER)
    assert view["status"] == "paid"
    assert (view["delivery"]["status"], view["delivery"]["packed_at"]) == ("pending", None)


async def test_courier_never_rewinds_before_acceptance(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_paid(world)
    resp = await _rewind(order["id"], "pending")
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "illegal_rewind"


async def test_door_orders_cannot_rewind_to_courier_stages(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    async with client_as(CUSTOMER) as ac:
        door = (await ac.post("/api/v1/orders", json={
            "customer_address_id": world.local_address_id, "store_id": world.store_id,
            "service_id": world.service_id, "payment_method": "upi",
        })).json()
    async with client_as(SELLER) as ac:
        await ac.post(f"/api/v1/orders/{door['id']}/transition", json={"to": "packed"})
    resp = await _rewind(door["id"], "paid")
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "illegal_rewind"


async def test_address_override_is_rejected_for_courier(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    async with client_as(ADMIN) as ac:
        resp = await ac.patch(f"/api/v1/admin/orders/{order['id']}/delivery-address", json={
            "address": {
                "address_line1": "9 New Road", "city": "Mysuru", "state": "Karnataka",
                "pincode": "570002", "country": "India", "latitude": 12.30, "longitude": 76.64,
            },
            "reason": "Customer phoned with a new flat number",
        })
    assert resp.status_code == 409
    assert resp.json()["detail"]["detail"] == "not_applicable_for_courier"


async def test_courier_orders_are_not_returnable(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    sps = await session.get(SellerProfileService, world.sps_id)
    assert sps is not None
    sps.return_window_days = 7  # returns are on for the service…
    await session.commit()
    order = await order_at_dispatched(world)
    async with client_as(CUSTOMER) as ac:
        assert (await ac.post(f"/api/v1/orders/{order['id']}/courier/received")).status_code == 200
    db_order = await session.get(Order, order["id"])
    assert db_order is not None
    await session.refresh(db_order)
    result = await returns_svc.compute_eligibility(
        session, order=db_order, customer_profile_id=world.customer_profile_id,
    )
    assert result.eligible is False
    assert result.reason_code == "not_returnable_courier"  # …but not for courier


async def test_order_value_fee_excludes_the_courier_charge(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await insert_courier_order(
        session, world, status=OrderStatus.Delivered, subtotal=200.0, delivery_fee=120.0,
    )
    link = await session.get(CustomerAddress, world.local_address_id)
    assert link is not None
    session.add(Order(
        customer_profile_id=world.customer_profile_id, store_id=world.store_id,
        service_id=world.service_id, service_name_snapshot="Sweets",
        delivery_address_id=link.address_id, delivery_address_snapshot="Bengaluru",
        delivery_mode=DeliveryMode.DoorDelivery, status=OrderStatus.Delivered,
        subtotal=200.0, delivery_fee=30.0, tax=0.0, total=230.0,
    ))
    await session.commit()
    today = ist_today()
    total = await compute_order_value_sales(
        session, world.store_id, world.service_id,
        today - timedelta(days=1), today + timedelta(days=1),
    )
    assert total == 430.0  # courier goods 200 + door 230 (its fee stays in)


async def test_admin_customer_orders_carry_the_delivery_mode(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    async with client_as(ADMIN) as ac:
        resp = await ac.get(f"/api/v1/admin/customers/{world.customer_profile_id}/orders")
    assert resp.status_code == 200, resp.text
    row = next(o for o in resp.json() if o["id"] == order["id"])
    assert (row["delivery_mode"], row["status"]) == ("courier", "pending")
