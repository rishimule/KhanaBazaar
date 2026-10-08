# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Seller payment settings: switches, method rules, generations and the
settings endpoints (spec 2026-10-07 §4, §5, §8)."""
from typing import Any

import httpx
from fastapi import HTTPException
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
    request_changes,
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
        "verification_status": VerificationStatus.Approved,
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


async def _file(
    session: AsyncSession, world: CourierWorld, group: SellerProfileChangeGroup,
    proposed: dict[str, Any],
) -> Any:
    seller = await _seller(session, world)
    res = await create_change_request(
        session=session, seller_profile=seller, group=group,
        proposed=proposed, note=None, actor_user_id=SELLER.id or 0,
    )
    await session.commit()
    return res.cr


async def _approve(
    session: AsyncSession, cr: Any, applied: dict[str, Any] | None = None
) -> None:
    await approve(session=session, cr=cr, admin_user_id=ADMIN.id or 0, applied=applied)
    await session.commit()


async def test_an_admin_clearing_the_upi_id_bumps_the_generation(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    cr = await _file(
        session, world, SellerProfileChangeGroup.Payments,
        {"upi_vpa": "ravi.new@okicici", "upi_enabled": True},
    )
    # A deliberate approve-with-edits removal (not an untouched empty request).
    await _approve(session, cr, applied={"upi_vpa": "", "upi_enabled": False})
    seller = await _seller(session, world)
    assert (seller.upi_vpa, seller.upi_enabled, seller.upi_generation) == (None, False, 1)


async def test_an_untouched_empty_payments_request_cannot_be_approved(
    session: AsyncSession,
) -> None:
    """The old Edit-button bug filed `{}`; approved as-is it would wipe UPI."""
    world = await seed_courier_world(session)
    cr = await _file(session, world, SellerProfileChangeGroup.Payments, {})
    try:
        await _approve(session, cr)
    except HTTPException as exc:
        assert (exc.status_code, exc.detail) == (422, "upi_vpa_required")
    else:
        raise AssertionError("approval should have been refused")
    await session.rollback()
    seller = await _seller(session, world)
    assert seller.upi_vpa == "ravi@okaxis" and seller.upi_enabled is True


async def test_approval_never_undoes_a_later_stop(session: AsyncSession) -> None:
    """A holder-name fix filed while bank transfer was on, then an emergency
    stop: approving the fix must not switch bank transfer back on."""
    world = await seed_courier_world(session)
    cr = await _file(
        session, world, SellerProfileChangeGroup.Banking,
        {"bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234",
         "bank_account_name": "Ravi Sweets Pvt", "bank_transfer_enabled": True},
    )
    assert (await _switch({"bank_transfer_enabled": False})).status_code == 200
    await _approve(session, cr)
    seller = await _seller(session, world)
    assert seller.bank_account_name == "Ravi Sweets Pvt"
    assert seller.bank_transfer_enabled is False and seller.bank_transfer_generation == 1


async def test_approval_never_switches_a_method_off(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _switch({"bank_transfer_enabled": False})
    cr = await _file(
        session, world, SellerProfileChangeGroup.Banking,
        {"bank_account_number": "123456789012", "bank_ifsc": "HDFC0002222",
         "bank_account_name": "Ravi Sweets", "bank_transfer_enabled": False},
    )
    assert (await _switch({"bank_transfer_enabled": True})).status_code == 200
    await _approve(session, cr)
    seller = await _seller(session, world)
    assert seller.bank_ifsc == "HDFC0002222"
    assert seller.bank_transfer_enabled is True and seller.bank_transfer_generation == 1


async def test_approval_switches_on_when_asked_and_nothing_stopped_since(
    session: AsyncSession,
) -> None:
    world = await seed_courier_world(session)
    await _switch({"bank_transfer_enabled": False})
    cr = await _file(
        session, world, SellerProfileChangeGroup.Banking,
        {"bank_account_number": "123456789012", "bank_ifsc": "HDFC0003333",
         "bank_account_name": "Ravi Sweets", "bank_transfer_enabled": True},
    )
    await _approve(session, cr)
    seller = await _seller(session, world)
    assert seller.bank_transfer_enabled is True and seller.bank_ifsc == "HDFC0003333"


async def test_a_new_upi_id_stays_off_after_a_stop_filed_later(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    cr = await _file(
        session, world, SellerProfileChangeGroup.Payments,
        {"upi_vpa": "ravi.new@okicici", "upi_enabled": True},
    )
    assert (await _switch({"upi_enabled": False})).status_code == 200
    await _approve(session, cr)
    seller = await _seller(session, world)
    assert seller.upi_vpa == "ravi.new@okicici" and seller.upi_enabled is False
    # The seller switches it back on themselves, instantly.
    assert (await _switch({"upi_enabled": True})).json()["upi_live"] is True


async def test_resubmitting_a_payments_request_needs_a_upi_id(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    cr = await _file(
        session, world, SellerProfileChangeGroup.Payments,
        {"upi_vpa": "ravi.new@okicici", "upi_enabled": True},
    )
    await request_changes(
        session=session, cr=cr, admin_user_id=ADMIN.id or 0, note="Please check the handle"
    )
    await session.commit()
    async with client_as(SELLER) as ac:
        r = await ac.patch(
            f"/api/v1/sellers/me/change-requests/{cr.id}/resubmit", json={"proposed": {}}
        )
    assert (r.status_code, r.json()["detail"]) == (422, "upi_vpa_required")


async def test_re_approval_does_not_undo_a_upi_stop(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    assert (await _switch({"upi_enabled": False})).status_code == 200
    async with client_as(ADMIN) as ac:
        rejected = await ac.patch(
            f"/api/v1/sellers/admin/{SELLER.id}/verify",
            json={"action": "reject", "rejection_reason": "Documents expired"},
        )
        approved = await ac.patch(
            f"/api/v1/sellers/admin/{SELLER.id}/verify", json={"action": "approve"}
        )
    assert rejected.status_code == 200 and approved.status_code == 200, approved.text
    seller = await _seller(session, world)
    assert seller.upi_enabled is False


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


def test_payees_count_only_for_an_approved_seller() -> None:
    """A revoked or resubmitting seller can write payee details directly, so
    none of it may reach a customer before an admin approves it again."""
    for status in (VerificationStatus.Pending, VerificationStatus.Rejected):
        seller = _profile(verification_status=status)
        assert not upi_live(seller) and not bank_transfer_live(seller)
        assert methods_for(seller, DeliveryMode.DoorDelivery) == [PaymentMethod.Cash]
        assert methods_for(seller, DeliveryMode.Courier) == []


async def test_a_combined_request_cannot_strand_door_delivery(session: AsyncSession) -> None:
    """The guard judges the state the whole request leaves behind."""
    await seed_courier_world(session)
    assert (await _switch({"bank_transfer_enabled": False})).status_code == 200
    r = await _switch({"cod_enabled": False, "upi_enabled": False})
    assert r.status_code == 409
    assert r.json()["detail"] == {"code": "last_payment_method", "mode": "door_delivery"}
    assert (await _settings())["upi_enabled"] is True  # nothing was written


async def test_admin_switch_off_bumps_the_generation(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    r = await _admin_switch({"bank_transfer_enabled": False, "reason": "Account reported frozen"})
    assert r.status_code == 200, r.text
    seller = await _seller(session, world)
    assert seller.bank_transfer_enabled is False and seller.bank_transfer_generation == 1


async def test_resubmitting_keeps_the_verification_qr_filed_with_the_request(
    session: AsyncSession,
) -> None:
    world = await seed_courier_world(session)
    cr = await _file(
        session, world, SellerProfileChangeGroup.Payments,
        {"upi_vpa": "ravi.new@okicici", "upi_enabled": True,
         "upi_qr_url": "/media/payments/1/qr.webp", "storage_key": "payments/1/qr.webp"},
    )
    await request_changes(
        session=session, cr=cr, admin_user_id=ADMIN.id or 0, note="Handle has a typo"
    )
    await session.commit()
    async with client_as(SELLER) as ac:
        r = await ac.patch(
            f"/api/v1/sellers/me/change-requests/{cr.id}/resubmit",
            json={"proposed": {"upi_vpa": "ravi.v2@okicici", "upi_enabled": True}},
        )
    assert r.status_code == 200, r.text
    proposed = r.json()["proposed_json"]
    assert proposed["upi_vpa"] == "ravi.v2@okicici"
    assert proposed["upi_qr_url"] == "/media/payments/1/qr.webp"
    assert proposed["storage_key"] == "payments/1/qr.webp"


async def test_approval_reads_the_switches_it_locked(session: AsyncSession) -> None:
    """The test session still holds the seller at UPI generation 0 while two
    requests stop and restart UPI (generation 1). Approval must act on the
    locked row, not that stale copy: clearing the ID bumps 1 → 2, so copies
    saved at generation 1 can never come back."""
    world = await seed_courier_world(session)
    cr = await _file(
        session, world, SellerProfileChangeGroup.Payments,
        {"upi_vpa": "ravi.new@okicici", "upi_enabled": True},
    )
    # Hold this session's copy, as the admin route does after loading the
    # seller: the identity map keeps objects only while something does.
    stale = await _seller(session, world)
    assert stale.upi_generation == 0
    assert (await _switch({"upi_enabled": False})).status_code == 200
    assert (await _switch({"upi_enabled": True})).status_code == 200
    await _approve(session, cr, applied={"upi_vpa": "", "upi_enabled": False})
    seller = await _seller(session, world)
    assert (seller.upi_vpa, seller.upi_enabled, seller.upi_generation) == (None, False, 2)


async def test_a_request_filed_before_generations_still_respects_a_stop(
    session: AsyncSession,
) -> None:
    """The old API filed baselines without generations; approval then falls
    back to "it was on at filing and is off now"."""
    world = await seed_courier_world(session)
    cr = await _file(
        session, world, SellerProfileChangeGroup.Banking,
        {"bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234",
         "bank_account_name": "Ravi Sweets Pvt", "bank_transfer_enabled": True},
    )
    cr.baseline_json = {
        k: v for k, v in cr.baseline_json.items() if k != "bank_transfer_generation"
    }
    session.add(cr)
    await session.commit()
    assert (await _switch({"bank_transfer_enabled": False})).status_code == 200
    await _approve(session, cr)
    seller = await _seller(session, world)
    assert seller.bank_account_name == "Ravi Sweets Pvt"
    assert seller.bank_transfer_enabled is False


async def test_approval_will_not_turn_bank_transfer_on_without_every_detail(
    session: AsyncSession,
) -> None:
    world = await seed_courier_world(session)
    assert (await _switch({"bank_transfer_enabled": False})).status_code == 200
    cr = await _file(
        session, world, SellerProfileChangeGroup.Banking,
        {"bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234",
         "bank_account_name": "Ravi Sweets", "bank_transfer_enabled": True},
    )
    try:
        await _approve(session, cr, applied={
            "bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234",
            "bank_account_name": "", "bank_transfer_enabled": True,
        })
    except HTTPException as exc:
        assert (exc.status_code, exc.detail) == (422, "bank_transfer_incomplete")
    else:
        raise AssertionError("approval should have been refused")
    await session.rollback()
    seller = await _seller(session, world)
    assert seller.bank_account_name == "Ravi Sweets" and seller.bank_transfer_enabled is False


async def test_a_banking_request_cannot_strand_live_bank_transfer(
    session: AsyncSession,
) -> None:
    """Approval never switches bank transfer off, so while it is on even a
    request that doesn't ask to turn it on must keep every detail — else no
    admin could approve it as filed."""
    world = await seed_courier_world(session)
    stranding = {
        "bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234",
        "bank_account_name": "", "bank_transfer_enabled": False,
    }
    try:
        await _file(session, world, SellerProfileChangeGroup.Banking, stranding)
    except HTTPException as exc:
        assert (exc.status_code, exc.detail) == (422, "bank_transfer_incomplete")
    else:
        raise AssertionError("filing should have been refused")
    await session.rollback()
    # Switched off first, the same request is fine.
    assert (await _switch({"bank_transfer_enabled": False})).status_code == 200
    cr = await _file(session, world, SellerProfileChangeGroup.Banking, stranding)
    assert cr.status.value == "submitted"


async def test_a_resubmission_after_a_stop_asks_again(session: AsyncSession) -> None:
    """A stop pulled after filing blocks the request's "turn on", but sending
    the request again (after the admin asked for changes) asks again."""
    world = await seed_courier_world(session)
    cr = await _file(
        session, world, SellerProfileChangeGroup.Payments,
        {"upi_vpa": "ravi.new@okicici", "upi_enabled": True},
    )
    assert (await _switch({"upi_enabled": False})).status_code == 200
    await request_changes(
        session=session, cr=cr, admin_user_id=ADMIN.id or 0, note="Handle has a typo"
    )
    await session.commit()
    async with client_as(SELLER) as ac:
        r = await ac.patch(
            f"/api/v1/sellers/me/change-requests/{cr.id}/resubmit",
            json={"proposed": {"upi_vpa": "ravi.v2@okicici", "upi_enabled": True}},
        )
    assert r.status_code == 200, r.text
    await session.refresh(cr)
    await _approve(session, cr)
    seller = await _seller(session, world)
    assert (seller.upi_vpa, seller.upi_enabled) == ("ravi.v2@okicici", True)
