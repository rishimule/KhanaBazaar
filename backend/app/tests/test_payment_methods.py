# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Seller payment settings: switches, method rules, generations and the
settings endpoints (spec 2026-10-07 §4, §5, §8)."""
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Payment
from app.models.profile import SellerProfile
from tests._courier_helpers import CourierWorld


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


from app.models.commerce import DeliveryMode, PaymentMethod  # noqa: E402
from app.services.payment_methods import (  # noqa: E402
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
