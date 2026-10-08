# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Payment methods at checkout and the payee saved on each order
(spec 2026-10-07 §5–§7)."""
from typing import Any

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.email_render import render_email
from app.models.commerce import Payment, PaymentStatus
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from app.services.serviceability import compute_locality, zone_for_point
from app.worker import _pay_block
from tests._courier_helpers import (
    ADMIN,
    COURIER_POINT,
    CUSTOMER,
    SELLER,
    CourierWorld,
    accept_quote,
    client_as,
    get_order,
    place_courier_order,
    seed_courier_world,
    send_quote,
)


async def _place_local(
    world: CourierWorld, method: str = "upi", mode: str = "door_delivery"
) -> httpx.Response:
    body: dict[str, Any] = {
        "store_id": world.store_id, "service_id": world.service_id,
        "payment_method": method, "delivery_mode": mode,
    }
    if mode == "door_delivery":
        body["customer_address_id"] = world.local_address_id
    async with client_as(CUSTOMER) as ac:
        return await ac.post("/api/v1/orders", json=body)


async def _payment(session: AsyncSession, order_id: int) -> Payment:
    payment = (await session.exec(select(Payment).where(Payment.order_id == order_id))).first()
    assert payment is not None
    await session.refresh(payment)
    return payment


async def _set(session: AsyncSession, world: CourierWorld, **fields: Any) -> None:
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    await session.refresh(seller)
    for name, value in fields.items():
        setattr(seller, name, value)
    session.add(seller)
    await session.commit()


async def _enable_pickup(session: AsyncSession, world: CourierWorld) -> None:
    sps = await session.get(SellerProfileService, world.sps_id)
    assert sps is not None
    sps.pickup_enabled = True
    session.add(sps)
    await session.commit()


async def test_a_switched_off_cash_is_refused_at_checkout(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _set(session, world, cod_enabled=False)
    r = await _place_local(world, "cash")
    assert (r.status_code, r.json()["detail"]) == (409, "cash_unavailable")


async def test_a_switched_off_pay_at_store_refuses_pickup(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _enable_pickup(session, world)
    await _set(session, world, pay_at_store_enabled=False)
    r = await _place_local(world, "pay_at_store", "pickup")
    assert (r.status_code, r.json()["detail"]) == (409, "pay_at_store_unavailable")


async def test_local_bank_transfer_needs_live_details(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _set(session, world, bank_transfer_enabled=False)
    r = await _place_local(world, "net_banking")
    assert (r.status_code, r.json()["detail"]) == (409, "bank_transfer_unavailable")


async def test_a_local_upi_order_saves_only_the_upi_payee(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    r = await _place_local(world, "upi")
    assert r.status_code == 201, r.text
    p = await _payment(session, r.json()["id"])
    assert (p.payee_upi_vpa, p.payee_upi_name, p.payee_upi_generation) == (
        "ravi@okaxis", "Ravi Sweets", 0,
    )
    assert p.payee_bank_account_number is None


async def test_a_local_bank_order_saves_only_the_bank_payee(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    r = await _place_local(world, "net_banking")
    assert r.status_code == 201, r.text
    p = await _payment(session, r.json()["id"])
    assert (p.payee_bank_account_name, p.payee_bank_account_number, p.payee_bank_ifsc) == (
        "Ravi Sweets", "123456789012", "HDFC0001234",
    )
    assert p.payee_upi_vpa is None


async def test_a_cash_order_saves_no_payee(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    r = await _place_local(world, "cash")
    assert r.status_code == 201, r.text
    p = await _payment(session, r.json()["id"])
    assert p.payee_upi_vpa is None and p.payee_bank_account_number is None


async def test_a_courier_order_saves_every_live_prepaid_payee(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    p = await _payment(session, order["id"])
    assert p.payee_upi_vpa == "ravi@okaxis"
    assert p.payee_bank_account_number == "123456789012"


async def test_store_read_offers_only_live_methods(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _set(session, world, bank_transfer_enabled=False, pay_at_store_enabled=False)
    async with client_as(CUSTOMER) as ac:
        body = (await ac.get(f"/api/v1/stores/{world.store_id}")).json()
    assert body["accepted_payment_methods"] == ["upi", "cash"]
    assert body["bank_transfer_payee"] is None
    await _set(session, world, bank_transfer_enabled=True)
    async with client_as(CUSTOMER) as ac:
        body = (await ac.get(f"/api/v1/stores/{world.store_id}")).json()
    assert body["bank_transfer_payee"] == {"account_name": "Ravi Sweets"}
    assert "account_number" not in body["bank_transfer_payee"]


async def _seller_switch(body: dict[str, Any]) -> None:
    async with client_as(SELLER) as ac:
        r = await ac.patch("/api/v1/sellers/me/payments/methods", json=body)
    assert r.status_code == 200, r.text


async def test_an_approved_change_never_redirects_a_placed_order(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = (await _place_local(world, "upi")).json()
    await _set(session, world, upi_vpa="ravi.new@okicici")  # as if an admin approved it
    body = await get_order(order["id"])
    assert body["payee"] == {
        "upi": {"vpa": "ravi@okaxis", "display_name": "Ravi Sweets"},
        "bank_transfer": None,
    }


async def test_an_off_switch_drops_the_saved_payee_for_good(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = (await _place_local(world, "upi")).json()
    await _seller_switch({"upi_enabled": False})
    assert (await get_order(order["id"]))["payee"] == {"upi": None, "bank_transfer": None}
    await _set(session, world, upi_vpa="ravi.new@okicici")
    await _seller_switch({"upi_enabled": True})
    assert (await get_order(order["id"]))["payee"]["upi"]["vpa"] == "ravi.new@okicici"


async def test_an_order_with_nothing_saved_shows_the_current_payee(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = (await _place_local(world, "upi")).json()
    p = await _payment(session, order["id"])
    p.payee_upi_vpa = None
    p.payee_upi_name = None
    p.payee_upi_generation = None
    session.add(p)
    await session.commit()
    await _set(session, world, upi_vpa="ravi.new@okicici")
    assert (await get_order(order["id"]))["payee"]["upi"]["vpa"] == "ravi.new@okicici"


async def test_bank_details_reach_the_customer_and_admins_only(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = (await _place_local(world, "net_banking")).json()
    mine = await get_order(order["id"])
    assert mine["payee"] == {
        "upi": None,
        "bank_transfer": {
            "account_name": "Ravi Sweets", "account_number": "123456789012", "ifsc": "HDFC0001234",
        },
    }
    assert mine["payee_record"] is None
    seller_view = await get_order(order["id"], as_user=SELLER)
    assert seller_view["payee"] is None and seller_view["payee_record"] is None
    admin_view = await get_order(order["id"], as_user=ADMIN)
    assert admin_view["payee"] is None
    assert admin_view["payee_record"]["bank_transfer"]["account_number"] == "123456789012"


async def test_payee_is_left_out_of_order_lists(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _place_local(world, "upi")
    async with client_as(CUSTOMER) as ac:
        listed = (await ac.get("/api/v1/orders")).json()["orders"]
    assert listed and listed[0]["payee"] is None


async def test_no_payee_once_paid(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = (await _place_local(world, "upi")).json()
    p = await _payment(session, order["id"])
    p.status = PaymentStatus.Paid
    session.add(p)
    await session.commit()
    assert (await get_order(order["id"]))["payee"] is None


async def test_no_payee_once_cancelled(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = (await _place_local(world, "upi")).json()
    async with client_as(CUSTOMER) as ac:
        r = await ac.post(f"/api/v1/orders/{order['id']}/cancel", json={})
    assert r.status_code == 200, r.text
    assert (await get_order(order["id"]))["payee"] is None


async def test_cash_orders_have_no_payee(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = (await _place_local(world, "cash")).json()
    assert (await get_order(order["id"]))["payee"] is None


async def _accept(order_id: int) -> None:
    quote = (await send_quote(order_id)).json()["courier"]["quotes"][0]
    assert (await accept_quote(order_id, quote["id"])).status_code == 200


async def test_a_courier_payee_appears_once_the_quote_is_accepted(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    assert (await get_order(order["id"]))["payee"] is None
    await _accept(order["id"])
    body = await get_order(order["id"])
    assert body["payee"]["upi"]["vpa"] == "ravi@okaxis"
    assert body["payee"]["bank_transfer"]["account_number"] == "123456789012"
    assert body["courier"]["bank_transfer"] == body["payee"]["bank_transfer"]


async def test_a_courier_method_turned_on_after_placing_uses_current_details(
    session: AsyncSession,
) -> None:
    world = await seed_courier_world(session)
    await _set(session, world, bank_transfer_enabled=False)
    order = await place_courier_order(world)
    assert (await _payment(session, order["id"])).payee_bank_account_number is None
    await _set(session, world, bank_transfer_enabled=True)
    await _accept(order["id"])
    body = await get_order(order["id"])
    assert body["payee"]["bank_transfer"]["account_number"] == "123456789012"


async def _claim(order_id: int) -> httpx.Response:
    async with client_as(CUSTOMER) as ac:
        return await ac.post(f"/api/v1/orders/{order_id}/payment/claim")


async def test_a_customer_can_claim_a_local_bank_transfer(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = (await _place_local(world, "net_banking")).json()
    first = await _claim(order["id"])
    again = await _claim(order["id"])
    assert first.status_code == 200, first.text
    claimed = first.json()["payment"]["customer_claimed_at"]
    assert claimed and again.json()["payment"]["customer_claimed_at"] == claimed
    assert first.json()["payment"]["status"] == "pending"


async def test_cash_orders_cannot_be_claimed(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = (await _place_local(world, "cash")).json()
    r = await _claim(order["id"])
    assert (r.status_code, r.json()["detail"]) == (409, "claim_not_applicable")


async def test_a_cancelled_order_cannot_be_claimed(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = (await _place_local(world, "upi")).json()
    async with client_as(CUSTOMER) as ac:
        assert (await ac.post(f"/api/v1/orders/{order['id']}/cancel", json={})).status_code == 200
    r = await _claim(order["id"])
    assert (r.status_code, r.json()["detail"]) == (409, "terminal_status")


def _ctx(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "order_total": 300.0, "store_credit_applied": 50.0, "payment_method": "upi",
        "delivery_mode": "door_delivery", "payee_upi_vpa": "ravi@okaxis",
        "payee_bank_live": True,
    }
    base.update(fields)
    return base


def test_pay_block_bills_the_net_amount_to_the_saved_upi_id() -> None:
    assert _pay_block(_ctx()) == {
        "upi_vpa": "ravi@okaxis", "upi_payable": 250.0, "bank_payable": None,
    }


def test_pay_block_for_a_bank_transfer_names_no_account() -> None:
    assert _pay_block(_ctx(payment_method="net_banking")) == {
        "upi_vpa": None, "upi_payable": None, "bank_payable": 250.0,
    }


def test_pay_block_is_empty_for_courier_stopped_or_fully_credited_orders() -> None:
    empty = {"upi_vpa": None, "upi_payable": None, "bank_payable": None}
    assert _pay_block(_ctx(delivery_mode="courier")) == empty
    assert _pay_block(_ctx(payment_method="net_banking", payee_bank_live=False)) == empty
    assert _pay_block(_ctx(store_credit_applied=300.0))["upi_payable"] is None


def _render(order: dict[str, Any]) -> Any:
    base = {
        "order_id": 7, "service_name": "Sweets", "store_name": "Ravi Sweets",
        "line_items": [], "order_total": 300.0, "subtotal": 300.0, "delivery_fee": 0.0,
        "delivery_eta": None, "preferred_delivery": None,
        "upi_vpa": None, "upi_payable": None,
    }
    base.update(order)
    return render_email(
        "order_placed_customer",
        {"orders": [base], "grand_total": 300.0, "customer_first_name": "Asha"},
        lang="en",
    )


def test_order_email_shows_a_bank_transfer_block_without_account_details() -> None:
    payload = _render({"bank_payable": 250.0})
    assert "by bank transfer" in payload.html and "250.00" in payload.html
    assert "by bank transfer" in payload.text
    assert "123456789012" not in payload.html


def test_order_email_renders_without_the_new_keys() -> None:
    payload = _render({})
    assert "by bank transfer" not in payload.html


async def test_a_revoked_sellers_payees_go_dark_everywhere(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = (await _place_local(world, "net_banking")).json()
    lat, lng = COURIER_POINT
    before = await compute_locality(session, lat=lat, lng=lng)
    assert any(world.store_id in ids for ids in before.courier.values())
    # The store stays active: only the seller's approval goes.
    await _set(session, world, verification_status=VerificationStatus.Rejected)
    async with client_as(CUSTOMER) as ac:
        store = (await ac.get(f"/api/v1/stores/{world.store_id}")).json()
    assert store["upi_payee"] is None and store["bank_transfer_payee"] is None
    assert store["accepted_payment_methods"] == ["cash", "pay_at_store"]
    assert store["courier_payment_methods"] == []
    # The order placed before the revocation stops showing the account.
    assert (await get_order(order["id"]))["payee"] == {"upi": None, "bank_transfer": None}
    # Courier listings use the SQL twin of the same rule (_PAYEE_LIVE_SQL);
    # single-store checks use the Python one.
    after = await compute_locality(session, lat=lat, lng=lng)
    assert not any(world.store_id in ids for ids in after.courier.values())
    zone = await zone_for_point(session, store_id=world.store_id, lat=lat, lng=lng)
    assert zone.zone == "none"


async def test_admins_keep_the_payee_record_after_an_admin_action(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = (await _place_local(world, "net_banking")).json()
    async with client_as(ADMIN) as ac:
        r = await ac.post(
            f"/api/v1/orders/{order['id']}/cancel", json={"reason": "Customer asked support"}
        )
    assert r.status_code == 200, r.text
    assert r.json()["payee_record"]["bank_transfer"]["account_number"] == "123456789012"


async def test_an_old_order_at_a_store_without_its_method_shows_no_panel(
    session: AsyncSession,
) -> None:
    """Placed before payees were saved ("Net Banking" was offered everywhere)
    at a store that doesn't take bank transfers: no "stopped" alarm."""
    world = await seed_courier_world(session)
    order = (await _place_local(world, "net_banking")).json()
    p = await _payment(session, order["id"])
    p.payee_bank_account_name = None
    p.payee_bank_account_number = None
    p.payee_bank_ifsc = None
    p.payee_bank_generation = None
    session.add(p)
    await session.commit()
    await _set(session, world, bank_transfer_enabled=False)
    assert (await get_order(order["id"]))["payee"] is None


async def test_an_old_upi_order_still_says_the_store_stopped(session: AsyncSession) -> None:
    """UPI always needed a live payee at checkout, so an old UPI order whose
    store stops UPI shows the "stopped" notice (and "I've paid"), not nothing."""
    world = await seed_courier_world(session)
    order = (await _place_local(world, "upi")).json()
    p = await _payment(session, order["id"])
    p.payee_upi_vpa = None
    p.payee_upi_name = None
    p.payee_upi_generation = None
    session.add(p)
    await session.commit()
    await _set(session, world, upi_enabled=False)
    assert (await get_order(order["id"]))["payee"] == {"upi": None, "bank_transfer": None}


async def test_pickup_orders_save_their_payee_too(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _enable_pickup(session, world)
    r = await _place_local(world, "upi", "pickup")
    assert r.status_code == 201, r.text
    assert (await _payment(session, r.json()["id"])).payee_upi_vpa == "ravi@okaxis"
    assert r.json()["payee"]["upi"]["vpa"] == "ravi@okaxis"


async def test_courier_payee_follows_an_off_switch_and_ends_once_paid(
    session: AsyncSession,
) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    await _accept(order["id"])
    await _seller_switch({"bank_transfer_enabled": False})
    body = await get_order(order["id"])
    assert body["payee"]["bank_transfer"] is None
    assert body["courier"]["bank_transfer"] is None
    assert body["payee"]["upi"]["vpa"] == "ravi@okaxis"
    async with client_as(SELLER) as ac:
        assert (await ac.post(f"/api/v1/orders/{order['id']}/payment/confirm")).status_code == 200
    assert (await get_order(order["id"]))["payee"] is None


async def test_pay_at_store_orders_cannot_be_claimed(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _enable_pickup(session, world)
    order = (await _place_local(world, "pay_at_store", "pickup")).json()
    r = await _claim(order["id"])
    assert (r.status_code, r.json()["detail"]) == (409, "claim_not_applicable")
