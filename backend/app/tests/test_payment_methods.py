# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Seller payment settings: switches, method rules, generations and the
settings endpoints (spec 2026-10-07 §4, §5, §8)."""
from typing import Any

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.admin_audit import AdminActionLog
from app.models.commerce import DeliveryMode, Payment, PaymentMethod
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from app.models.seller_profile_change_request import SellerProfileChangeGroup
from app.services.courier_settings import apply_bank_fields
from app.services.payment_methods import (
    BankPayee,
    UpiPayee,
    bank_transfer_live,
    effective_bank,
    effective_upi,
    methods_for,
    saved_bank,
    saved_upi,
    set_bank_transfer_enabled,
    set_upi_enabled,
    snapshot_payee,
    store_accepted_methods,
    upi_live,
)
from app.services.seller_profile_change_requests import (
    approve,
    create_change_request,
)
from tests._courier_helpers import (
    ADMIN,
    SELLER,
    CourierWorld,
    client_as,
    seed_courier_world,
)


def _profile(**fields: Any) -> SellerProfile:
    """An unsaved seller with every method live unless overridden."""
    base: dict[str, Any] = {
        "user_id": 1, "first_name": "Ravi", "phone": "+919900000002",
        "business_name": "Ravi Sweets", "business_address_id": 1,
        "upi_vpa": "ravi@okaxis", "upi_enabled": True,
        "bank_account_name": "Ravi Sweets", "bank_account_number": "123456789012",
        "bank_ifsc": "HDFC0001234", "bank_transfer_enabled": True,
    }
    base.update(fields)
    return SellerProfile(**base)


async def _seller(session: AsyncSession, world: CourierWorld) -> SellerProfile:
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    await session.refresh(seller)
    return seller


def test_new_switches_start_on_and_generations_at_zero() -> None:
    seller = _profile()
    assert seller.cod_enabled is True and seller.pay_at_store_enabled is True
    assert seller.upi_generation == 0 and seller.bank_transfer_generation == 0


def test_payment_carries_a_saved_payee() -> None:
    assert {
        "payee_upi_vpa", "payee_upi_name", "payee_upi_generation",
        "payee_bank_account_name", "payee_bank_account_number",
        "payee_bank_ifsc", "payee_bank_generation",
    } <= set(Payment.model_fields)


def test_mode_methods_follow_the_switches() -> None:
    seller = _profile()
    assert methods_for(seller, DeliveryMode.DoorDelivery) == [
        PaymentMethod.Upi, PaymentMethod.NetBanking, PaymentMethod.Cash,
    ]
    assert methods_for(seller, DeliveryMode.Pickup) == [
        PaymentMethod.Upi, PaymentMethod.NetBanking, PaymentMethod.PayAtStore,
    ]
    assert methods_for(seller, DeliveryMode.Courier) == [PaymentMethod.Upi, PaymentMethod.NetBanking]
    off = _profile(upi_enabled=False, cod_enabled=False, pay_at_store_enabled=False)
    assert methods_for(off, DeliveryMode.DoorDelivery) == [PaymentMethod.NetBanking]
    assert methods_for(off, DeliveryMode.Pickup) == [PaymentMethod.NetBanking]


def test_bank_transfer_needs_every_detail_and_upi_a_payee() -> None:
    assert not bank_transfer_live(_profile(bank_account_name=None))
    assert not bank_transfer_live(_profile(bank_ifsc=""))
    assert not bank_transfer_live(_profile(bank_transfer_enabled=False))
    assert bank_transfer_live(_profile())
    assert not upi_live(_profile(upi_vpa=None))


def test_store_accepted_methods_lists_live_local_methods_in_order() -> None:
    assert store_accepted_methods(_profile(bank_transfer_enabled=False)) == [
        PaymentMethod.Upi, PaymentMethod.Cash, PaymentMethod.PayAtStore,
    ]
    assert store_accepted_methods(
        _profile(upi_enabled=False, bank_transfer_enabled=False,
                 cod_enabled=False, pay_at_store_enabled=False)
    ) == []


def test_only_an_on_to_off_move_bumps_a_generation() -> None:
    seller = _profile()
    set_upi_enabled(seller, True)
    set_upi_enabled(seller, False)
    set_upi_enabled(seller, False)
    set_upi_enabled(seller, True)
    set_bank_transfer_enabled(seller, False)
    assert (seller.upi_generation, seller.bank_transfer_generation) == (1, 1)
    assert seller.upi_enabled is True and seller.bank_transfer_enabled is False


def test_snapshot_saves_the_chosen_local_method_only() -> None:
    seller = _profile(upi_generation=3)
    upi = Payment(order_id=1, amount=1.0)
    snapshot_payee(upi, seller, mode=DeliveryMode.DoorDelivery, method=PaymentMethod.Upi)
    assert (upi.payee_upi_vpa, upi.payee_upi_name, upi.payee_upi_generation) == (
        "ravi@okaxis", "Ravi Sweets", 3,
    )
    assert upi.payee_bank_account_number is None
    bank = Payment(order_id=1, amount=1.0)
    snapshot_payee(bank, seller, mode=DeliveryMode.Pickup, method=PaymentMethod.NetBanking)
    assert (bank.payee_bank_account_number, bank.payee_bank_generation) == ("123456789012", 0)
    assert bank.payee_upi_vpa is None
    cash = Payment(order_id=1, amount=1.0)
    snapshot_payee(cash, seller, mode=DeliveryMode.DoorDelivery, method=PaymentMethod.Cash)
    assert cash.payee_upi_vpa is None and cash.payee_bank_account_number is None


def test_snapshot_saves_every_live_prepaid_method_for_courier() -> None:
    payment = Payment(order_id=1, amount=1.0)
    snapshot_payee(
        payment, _profile(bank_transfer_enabled=False),
        mode=DeliveryMode.Courier, method=PaymentMethod.Upi,
    )
    assert payment.payee_upi_vpa == "ravi@okaxis"
    assert payment.payee_bank_account_number is None


def test_effective_upi_keeps_the_saved_payee_until_an_off_switch() -> None:
    seller = _profile()
    payment = Payment(order_id=1, amount=1.0)
    snapshot_payee(payment, seller, mode=DeliveryMode.DoorDelivery, method=PaymentMethod.Upi)
    seller.upi_vpa = "ravi.new@okicici"  # an approved change
    assert effective_upi(payment, seller) == UpiPayee("ravi@okaxis", "Ravi Sweets")
    set_upi_enabled(seller, False)  # the emergency stop
    assert effective_upi(payment, seller) is None
    set_upi_enabled(seller, True)  # back on: the old saved ID never returns
    assert effective_upi(payment, seller) == UpiPayee("ravi.new@okicici", "Ravi Sweets")
    # An order with nothing saved (placed before release) shows the current one.
    assert effective_upi(Payment(order_id=1, amount=1.0), seller) == UpiPayee(
        "ravi.new@okicici", "Ravi Sweets",
    )


def test_effective_bank_follows_the_same_rules() -> None:
    seller = _profile()
    payment = Payment(order_id=1, amount=1.0)
    snapshot_payee(payment, seller, mode=DeliveryMode.DoorDelivery, method=PaymentMethod.NetBanking)
    seller.bank_account_number = "999988887777"
    assert effective_bank(payment, seller) == BankPayee("Ravi Sweets", "123456789012", "HDFC0001234")
    set_bank_transfer_enabled(seller, False)
    assert effective_bank(payment, seller) is None
    set_bank_transfer_enabled(seller, True)
    assert effective_bank(payment, seller) == BankPayee("Ravi Sweets", "999988887777", "HDFC0001234")


def test_saved_payee_is_the_raw_record() -> None:
    payment = Payment(order_id=1, amount=1.0, payee_upi_vpa="a1@ybl", payee_upi_name="A")
    assert saved_upi(payment) == UpiPayee("a1@ybl", "A")
    assert saved_bank(payment) is None


async def test_disable_route_bumps_the_upi_generation(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    async with client_as(SELLER) as ac:
        r = await ac.patch("/api/v1/sellers/me/payments/disable")
    assert r.status_code == 200, r.text
    seller = await _seller(session, world)
    assert seller.upi_enabled is False and seller.upi_generation == 1


async def test_a_sellers_payments_request_must_name_a_upi_id(session: AsyncSession) -> None:
    await seed_courier_world(session)
    async with client_as(SELLER) as ac:
        r = await ac.post(
            "/api/v1/sellers/me/change-requests",
            json={"group": "payments", "proposed": {}},
        )
    assert r.status_code == 422
    assert r.json()["detail"] == "upi_vpa_required"


async def test_an_approved_upi_removal_bumps_the_generation(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    seller = await _seller(session, world)
    res = await create_change_request(
        session=session, seller_profile=seller, group=SellerProfileChangeGroup.Payments,
        proposed={"upi_vpa": "", "upi_enabled": False}, note=None, actor_user_id=SELLER.id or 0,
    )
    await session.commit()
    await approve(session=session, cr=res.cr, admin_user_id=ADMIN.id or 0)
    await session.commit()
    seller = await _seller(session, world)
    assert (seller.upi_vpa, seller.upi_enabled, seller.upi_generation) == (None, False, 1)


def test_apply_bank_fields_turning_off_bumps_the_generation() -> None:
    seller = _profile()
    apply_bank_fields(seller, name=None, enabled=False)
    assert seller.bank_transfer_generation == 1


async def test_profile_reports_every_switch(session: AsyncSession) -> None:
    await seed_courier_world(session)
    async with client_as(SELLER) as ac:
        body = (await ac.get("/api/v1/sellers/me/profile")).json()
    assert body["upi_enabled"] is True
    assert body["cod_enabled"] is True and body["pay_at_store_enabled"] is True


async def _settings() -> dict[str, Any]:
    async with client_as(SELLER) as ac:
        r = await ac.get("/api/v1/sellers/me/payments")
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


async def _switch(body: dict[str, Any]) -> httpx.Response:
    async with client_as(SELLER) as ac:
        return await ac.patch("/api/v1/sellers/me/payments/methods", json=body)


async def _admin_switch(body: dict[str, Any]) -> httpx.Response:
    async with client_as(ADMIN) as ac:
        return await ac.patch(f"/api/v1/sellers/admin/{SELLER.id}/payments/methods", json=body)


async def test_settings_report_switches_and_methods_by_mode(session: AsyncSession) -> None:
    await seed_courier_world(session)
    s = await _settings()
    assert s["upi_live"] and s["bank_transfer_live"] and s["bank_details_complete"]
    assert s["cod_enabled"] and s["pay_at_store_enabled"]
    assert s["methods_by_mode"]["door_delivery"] == ["upi", "net_banking", "cash"]
    assert "pickup" not in s["methods_by_mode"]  # no service offers pickup
    assert s["methods_by_mode"]["courier"] == ["upi", "net_banking"]
    assert s["pickup_offered"] is False and s["courier_offered"] is True


async def test_turning_cash_off_updates_door_methods(session: AsyncSession) -> None:
    await seed_courier_world(session)
    r = await _switch({"cod_enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["methods_by_mode"]["door_delivery"] == ["upi", "net_banking"]


async def test_the_last_way_to_pay_for_door_delivery_is_kept(session: AsyncSession) -> None:
    await seed_courier_world(session)
    assert (await _switch({"upi_enabled": False, "bank_transfer_enabled": False})).status_code == 200
    r = await _switch({"cod_enabled": False})
    assert r.status_code == 409
    assert r.json()["detail"] == {"code": "last_payment_method", "mode": "door_delivery"}


async def test_pay_at_store_guard_binds_only_while_pickup_is_offered(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _switch({"upi_enabled": False, "bank_transfer_enabled": False})
    assert (await _switch({"pay_at_store_enabled": False})).status_code == 200
    assert (await _switch({"pay_at_store_enabled": True})).status_code == 200
    sps = await session.get(SellerProfileService, world.sps_id)
    assert sps is not None
    sps.pickup_enabled = True
    session.add(sps)
    await session.commit()
    r = await _switch({"pay_at_store_enabled": False})
    assert r.status_code == 409
    assert r.json()["detail"] == {"code": "last_payment_method", "mode": "pickup"}


async def test_payee_off_switches_are_never_refused(session: AsyncSession) -> None:
    await seed_courier_world(session)
    assert (await _switch({"cod_enabled": False, "bank_transfer_enabled": False})).status_code == 200
    r = await _switch({"upi_enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["methods_by_mode"]["door_delivery"] == []


async def test_switching_on_needs_approved_details(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    seller = await _seller(session, world)
    seller.upi_vpa = None
    seller.upi_enabled = False
    seller.bank_account_name = None
    seller.bank_transfer_enabled = False
    session.add(seller)
    await session.commit()
    upi = await _switch({"upi_enabled": True})
    bank = await _switch({"bank_transfer_enabled": True})
    assert (upi.status_code, upi.json()["detail"]) == (409, "upi_payee_missing")
    assert (bank.status_code, bank.json()["detail"]) == (409, "bank_transfer_incomplete")


async def test_only_an_approved_seller_switches_on(session: AsyncSession) -> None:
    await seed_courier_world(session, seller_status=VerificationStatus.Pending)
    assert (await _switch({"upi_enabled": False})).status_code == 200
    r = await _switch({"upi_enabled": True})
    assert (r.status_code, r.json()["detail"]) == (409, "seller_not_active")


async def test_an_empty_switch_request_changes_nothing(session: AsyncSession) -> None:
    await seed_courier_world(session)
    r = await _switch({})
    assert r.status_code == 200 and r.json()["cod_enabled"] is True


async def test_switching_upi_off_twice_bumps_the_generation_once(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _switch({"upi_enabled": False})
    await _switch({"upi_enabled": False})
    await _switch({"upi_enabled": True})
    seller = await _seller(session, world)
    assert seller.upi_enabled is True and seller.upi_generation == 1


async def test_admin_switches_need_a_reason_and_are_audited(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    short = await _admin_switch({"upi_enabled": False, "reason": "too short"})
    assert short.status_code == 422
    r = await _admin_switch({"upi_enabled": False, "reason": "Seller reported the UPI ID stolen"})
    assert r.status_code == 200, r.text
    assert r.json()["upi_enabled"] is False
    rows = (
        await session.exec(
            select(AdminActionLog).where(AdminActionLog.action == "payments.set_methods")
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].target_seller_id == world.seller_profile_id
    assert rows[0].before_json == {**rows[0].after_json, "upi_enabled": True}  # type: ignore[dict-item]
    assert rows[0].reason == "Seller reported the UPI ID stolen"


async def test_admin_can_stop_a_non_approved_sellers_upi_but_not_start_it(
    session: AsyncSession,
) -> None:
    await seed_courier_world(session, seller_status=VerificationStatus.Rejected)
    off = await _admin_switch({"upi_enabled": False, "reason": "Stopping payments for a review"})
    assert off.status_code == 200, off.text
    on = await _admin_switch({"upi_enabled": True, "reason": "Turning payments back on now"})
    assert (on.status_code, on.json()["detail"]) == (409, "seller_not_active")


async def test_admin_payment_routes_are_admin_only(session: AsyncSession) -> None:
    await seed_courier_world(session)
    async with client_as(SELLER) as ac:
        r = await ac.get(f"/api/v1/sellers/admin/{SELLER.id}/payments")
    assert r.status_code == 403
    async with client_as(ADMIN) as ac:
        ok = await ac.get(f"/api/v1/sellers/admin/{SELLER.id}/payments")
    assert ok.status_code == 200 and ok.json()["bank_account_number"] == "123456789012"
