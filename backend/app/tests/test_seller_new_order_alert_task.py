# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any
from unittest.mock import patch

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.whatsapp_templates import TEMPLATES
from app.models.address import Address
from app.models.base import AccountStatus, User, UserRole
from app.models.commerce import Order, OrderStatus
from app.models.profile import CustomerProfile, SellerProfile, VerificationStatus
from app.models.store import Store
from app.worker import seller_new_order_alert
from tests._helpers import make_address


def test_seller_new_order_template_registered() -> None:
    tmpl = TEMPLATES["seller_new_order"]
    assert tmpl.category == "UTILITY"
    assert set(tmpl.variables) == {"order_id", "amount"}
    rendered = tmpl.render({"order_id": "42", "amount": "350.00"})
    assert "#42" in rendered
    assert "350.00" in rendered


def test_dispatch_order_placed_fires_the_seller_alert() -> None:
    from app.services import order_emails

    with patch.object(order_emails, "_safe_delay") as safe_delay:
        order_emails.dispatch_order_placed([7])

    dispatched = [c.args[0].name for c in safe_delay.call_args_list]
    assert "send_seller_new_order_alert_async" in dispatched


class _RecordingSMS:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def send(self, to: str, text: str) -> None:
        self.calls.append((to, text))


async def _seed_order(
    session: AsyncSession, *, account_status: AccountStatus, phone: str
) -> int:
    """One approved seller with a store and one pending order. Returns order id."""
    seller = User(
        email=f"alert-{phone[-4:]}@kb.com",
        role=UserRole.Seller,
        is_active=account_status == AccountStatus.active,
        account_status=account_status,
    )
    customer = User(
        email=f"alert-cust-{phone[-4:]}@kb.com", role=UserRole.Customer, is_active=True
    )
    session.add_all([seller, customer])
    await session.flush()

    addrs = [Address(**make_address(pincode="560061")) for _ in range(3)]
    session.add_all(addrs)
    await session.flush()

    profile = SellerProfile(
        user_id=seller.id,
        first_name="Alert",
        phone=phone,
        business_name="Alert Store",
        verification_status=VerificationStatus.Approved,
        business_address_id=addrs[0].id,
    )
    cust_profile = CustomerProfile(user_id=customer.id, first_name="C")
    session.add_all([profile, cust_profile])
    await session.flush()

    store = Store(
        name="Alert Store", seller_profile_id=profile.id, address_id=addrs[1].id
    )
    session.add(store)
    await session.flush()

    from tests.test_carts import _seed_product

    _product, service_id = await _seed_product(
        session,
        service_slug="grocery",
        category_slug="food",
        subcategory_slug="fruit",
        product_slug="apple",
        name="Apple",
        base_price=50.0,
    )

    order = Order(
        customer_profile_id=cust_profile.id,
        store_id=store.id,
        service_id=service_id,
        service_name_snapshot="Grocery",
        delivery_address_id=addrs[2].id,
        status=OrderStatus.Pending,
        subtotal=120.0,
        delivery_fee=0.0,
        tax=0.0,
        total=120.0,
        delivery_address_snapshot="somewhere",
    )
    session.add(order)
    await session.commit()
    assert order.id is not None
    return order.id


@pytest.mark.asyncio
async def test_task_sends_sms_when_whatsapp_disabled(session: AsyncSession) -> None:
    """Exercises the task's real join + row unpack, not just its registration."""
    order_id = await _seed_order(
        session, account_status=AccountStatus.active, phone="+919812300011"
    )
    sms = _RecordingSMS()
    with patch("app.core.sms.get_sms_sender", lambda: sms), patch(
        "app.core.whatsapp.get_whatsapp_sender", lambda: None
    ):
        await seller_new_order_alert(order_id)

    assert len(sms.calls) == 1
    to, text = sms.calls[0]
    assert to == "+919812300011"
    assert f"#{order_id}" in text
    assert "120.00" in text
    # ASCII only: a rupee sign would push the SMS out of GSM-7 and double the
    # per-order segment cost.
    assert text.isascii(), text


@pytest.mark.asyncio
async def test_task_prefers_whatsapp_when_enabled(session: AsyncSession) -> None:
    order_id = await _seed_order(
        session, account_status=AccountStatus.active, phone="+919812300022"
    )
    sms = _RecordingSMS()
    sent: list[tuple[str, str, dict[str, str]]] = []

    class _WA:
        async def send_template(
            self, to: str, template: Any, variables: dict[str, str]
        ) -> None:
            sent.append((to, template.name, variables))

    with patch("app.core.sms.get_sms_sender", lambda: sms), patch(
        "app.core.whatsapp.get_whatsapp_sender", lambda: _WA()
    ):
        await seller_new_order_alert(order_id)

    assert sent == [
        ("+919812300022", "seller_new_order", {"order_id": str(order_id), "amount": "120.00"})
    ]
    assert sms.calls == []


@pytest.mark.asyncio
async def test_task_skips_non_active_seller_account(session: AsyncSession) -> None:
    """A suspended seller must not keep drawing billable messages."""
    order_id = await _seed_order(
        session, account_status=AccountStatus.suspended, phone="+919812300033"
    )
    sms = _RecordingSMS()
    with patch("app.core.sms.get_sms_sender", lambda: sms), patch(
        "app.core.whatsapp.get_whatsapp_sender", lambda: None
    ):
        await seller_new_order_alert(order_id)

    assert sms.calls == []


@pytest.mark.asyncio
async def test_task_noops_for_unknown_order(session: AsyncSession) -> None:
    sms = _RecordingSMS()
    with patch("app.core.sms.get_sms_sender", lambda: sms), patch(
        "app.core.whatsapp.get_whatsapp_sender", lambda: None
    ):
        await seller_new_order_alert(999_999)

    assert sms.calls == []


@pytest.mark.asyncio
async def test_hourly_quota_caps_the_billable_channel(session: AsyncSession) -> None:
    """Order spam must not bill an unbounded number of messages."""
    order_id = await _seed_order(
        session, account_status=AccountStatus.active, phone="+919812300044"
    )
    sms = _RecordingSMS()
    with patch("app.core.sms.get_sms_sender", lambda: sms), patch(
        "app.core.whatsapp.get_whatsapp_sender", lambda: None
    ), patch.object(settings, "SELLER_NEW_ORDER_ALERT_MAX_PER_HOUR", 2):
        for _ in range(5):
            await seller_new_order_alert(order_id)

    assert len(sms.calls) == 2


@pytest.mark.asyncio
async def test_quota_check_fails_open(session: AsyncSession) -> None:
    """A Redis outage must never silence a real order alert."""
    order_id = await _seed_order(
        session, account_status=AccountStatus.active, phone="+919812300055"
    )

    async def _boom() -> None:
        raise RuntimeError("redis down")

    sms = _RecordingSMS()
    with patch("app.core.sms.get_sms_sender", lambda: sms), patch(
        "app.core.whatsapp.get_whatsapp_sender", lambda: None
    ), patch("app.core.redis.get_redis", _boom):
        await seller_new_order_alert(order_id)

    assert len(sms.calls) == 1
