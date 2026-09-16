# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
"""Customer-facing UPI surface: StoreRead payee exposure, checkout
enforcement, and the "I've paid" claim endpoint."""
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app


# ── StoreRead payee exposure ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_store_read_omits_upi_without_payee(
    approved_seller_with_store: Any,
    session: AsyncSession,
) -> None:
    bundle = approved_seller_with_store
    # Explicitly clear the fixture's default payee: this test is *about* the
    # no-payee case, so it must not silently inherit one.
    bundle.profile.upi_vpa = None
    bundle.profile.upi_enabled = False
    session.add(bundle.profile)
    await session.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/api/v1/stores/{bundle.store.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "upi" not in body["accepted_payment_methods"]
    assert body["upi_payee"] is None


@pytest.mark.asyncio
async def test_store_read_exposes_payee_when_enabled(
    approved_seller_with_store: Any,
    session: AsyncSession,
) -> None:
    bundle = approved_seller_with_store
    bundle.profile.upi_vpa = "ganesh@okhdfcbank"
    bundle.profile.upi_enabled = True
    session.add(bundle.profile)
    await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/api/v1/stores/{bundle.store.id}")
    body = r.json()
    assert "upi" in body["accepted_payment_methods"]
    assert body["upi_payee"]["vpa"] == "ganesh@okhdfcbank"
    assert body["upi_payee"]["display_name"] == bundle.profile.business_name


@pytest.mark.asyncio
async def test_store_read_hides_payee_when_disabled(
    approved_seller_with_store: Any,
    session: AsyncSession,
) -> None:
    """A VPA on file but disabled must not be offered — this is the
    compromised-handle path from the immediate-disable route."""
    bundle = approved_seller_with_store
    bundle.profile.upi_vpa = "ganesh@okhdfcbank"
    bundle.profile.upi_enabled = False
    session.add(bundle.profile)
    await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/api/v1/stores/{bundle.store.id}")
    body = r.json()
    assert "upi" not in body["accepted_payment_methods"]
    assert body["upi_payee"] is None


@pytest.mark.asyncio
async def test_accepted_methods_never_include_credit(
    approved_seller_with_store: Any,
) -> None:
    """Credit eligibility is per-customer, not per-store — putting it in a
    cacheable store payload would leak one customer's standing."""
    bundle = approved_seller_with_store
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/api/v1/stores/{bundle.store.id}")
    assert "credit" not in r.json()["accepted_payment_methods"]


# ── Checkout enforcement ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_validate_upi_payee_rejects_payeeless_store(
    approved_seller_with_store: Any,
    session: AsyncSession,
) -> None:
    from fastapi import HTTPException

    from app.services.checkout import _validate_upi_payee_for_store

    bundle = approved_seller_with_store
    # Explicitly clear the fixture's default payee: this test is *about* the
    # no-payee case, so it must not silently inherit one.
    bundle.profile.upi_vpa = None
    bundle.profile.upi_enabled = False
    session.add(bundle.profile)
    await session.commit()
    with pytest.raises(HTTPException) as exc:
        await _validate_upi_payee_for_store(session, bundle.store.id)
    assert exc.value.status_code == 409
    assert exc.value.detail == "upi_unavailable"


@pytest.mark.asyncio
async def test_validate_upi_payee_passes_with_live_payee(
    approved_seller_with_store: Any,
    session: AsyncSession,
) -> None:
    from app.services.checkout import _validate_upi_payee_for_store

    bundle = approved_seller_with_store
    bundle.profile.upi_vpa = "ganesh@okhdfcbank"
    bundle.profile.upi_enabled = True
    session.add(bundle.profile)
    await session.commit()
    await _validate_upi_payee_for_store(session, bundle.store.id)


@pytest.mark.asyncio
async def test_validate_upi_payee_rejects_disabled_payee(
    approved_seller_with_store: Any,
    session: AsyncSession,
) -> None:
    """Disabled-but-stored VPA must not allow a UPI order through."""
    from fastapi import HTTPException

    from app.services.checkout import _validate_upi_payee_for_store

    bundle = approved_seller_with_store
    bundle.profile.upi_vpa = "ganesh@okhdfcbank"
    bundle.profile.upi_enabled = False
    session.add(bundle.profile)
    await session.commit()
    with pytest.raises(HTTPException) as exc:
        await _validate_upi_payee_for_store(session, bundle.store.id)
    assert exc.value.detail == "upi_unavailable"


# ── "I've paid" claim endpoint ────────────────────────────────────────
class _OrderBundle:
    def __init__(self, user: Any, order: Any) -> None:
        self.user = user
        self.order = order


async def _make_order(
    session: AsyncSession, bundle: Any, *, method: str
) -> _OrderBundle:
    """Insert a customer + a minimal Order/Payment pair directly.

    The claim endpoint only needs an owned order and its payment row, so this
    deliberately skips the cart/checkout path — those are covered elsewhere.
    """
    import uuid as _uuid

    from app.models.address import Address
    from app.models.base import User, UserRole
    from app.models.commerce import (
        Delivery,
        DeliveryStatus,
        Order,
        Payment,
        PaymentMethod,
        PaymentStatus,
    )
    from app.models.profile import CustomerProfile
    from tests._helpers import make_address

    user = User(
        email=f"c-{_uuid.uuid4().hex[:8]}@x.test",
        role=UserRole.Customer,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    profile = CustomerProfile(user_id=user.id, first_name="Cust")
    session.add(profile)
    addr = Address(**make_address())
    session.add(addr)
    await session.flush()

    order = Order(
        customer_profile_id=profile.id,
        store_id=bundle.store.id,
        service_id=bundle.service_id,
        service_name_snapshot="Grocery",
        delivery_address_id=addr.id,
        subtotal=1247.50,
        delivery_fee=0.0,
        tax=0.0,
        total=1247.50,
        delivery_address_snapshot="somewhere",
    )
    session.add(order)
    await session.flush()
    session.add(
        Payment(
            order_id=order.id,
            amount=order.total,
            method=PaymentMethod(method),
            status=PaymentStatus.Pending,
        )
    )
    # _serialize_order 500s on an order with no delivery row, so a realistic
    # order needs one even though the claim endpoint never reads it.
    session.add(Delivery(order_id=order.id, status=DeliveryStatus.Pending))
    await session.commit()
    await session.refresh(order)
    return _OrderBundle(user, order)


@pytest.mark.asyncio
async def test_claim_sets_timestamp_without_touching_status(
    approved_seller_with_store: Any,
    session: AsyncSession,
) -> None:
    """The claim is a customer assertion, never evidence — status must stay
    pending so the existing delivery-settles-payment machinery is untouched."""
    from sqlmodel import select

    from app.core.security import get_current_user
    from app.models.commerce import Payment, PaymentStatus

    ob = await _make_order(session, approved_seller_with_store, method="upi")
    app.dependency_overrides[get_current_user] = lambda: ob.user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(f"/api/v1/orders/{ob.order.id}/payment/claim")
        assert r.status_code == 200, r.text
        assert r.json()["payment"]["customer_claimed_at"] is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    payment = (
        await session.exec(select(Payment).where(Payment.order_id == ob.order.id))
    ).first()
    assert payment is not None
    assert payment.customer_claimed_at is not None
    assert payment.status is PaymentStatus.Pending


@pytest.mark.asyncio
async def test_claim_is_idempotent(
    approved_seller_with_store: Any, session: AsyncSession
) -> None:
    from app.core.security import get_current_user

    ob = await _make_order(session, approved_seller_with_store, method="upi")
    app.dependency_overrides[get_current_user] = lambda: ob.user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            first = await ac.post(f"/api/v1/orders/{ob.order.id}/payment/claim")
            second = await ac.post(f"/api/v1/orders/{ob.order.id}/payment/claim")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert first.status_code == 200
    assert second.status_code == 200
    # Re-tapping must not move the timestamp.
    assert (
        first.json()["payment"]["customer_claimed_at"]
        == second.json()["payment"]["customer_claimed_at"]
    )


@pytest.mark.asyncio
async def test_claim_rejects_other_customers_order(
    approved_seller_with_store: Any, session: AsyncSession
) -> None:
    """403, not 404: `_load_order_for_user` reserves 404 for a missing order
    and raises 403 when the order exists but belongs to someone else."""
    from app.core.security import get_current_user

    ob = await _make_order(session, approved_seller_with_store, method="upi")
    intruder = await _make_order(session, approved_seller_with_store, method="upi")

    app.dependency_overrides[get_current_user] = lambda: intruder.user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(f"/api/v1/orders/{ob.order.id}/payment/claim")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_claim_rejects_non_upi_order(
    approved_seller_with_store: Any, session: AsyncSession
) -> None:
    from app.core.security import get_current_user

    ob = await _make_order(session, approved_seller_with_store, method="cash")
    app.dependency_overrides[get_current_user] = lambda: ob.user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(f"/api/v1/orders/{ob.order.id}/payment/claim")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 409
    assert r.json()["detail"] == "not_upi_order"


@pytest.mark.asyncio
async def test_claim_rejects_settled_payment(
    approved_seller_with_store: Any, session: AsyncSession
) -> None:
    from sqlmodel import select

    from app.core.security import get_current_user
    from app.models.commerce import Payment, PaymentStatus

    ob = await _make_order(session, approved_seller_with_store, method="upi")
    payment = (
        await session.exec(select(Payment).where(Payment.order_id == ob.order.id))
    ).first()
    assert payment is not None
    payment.status = PaymentStatus.Paid
    session.add(payment)
    await session.commit()

    app.dependency_overrides[get_current_user] = lambda: ob.user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(f"/api/v1/orders/{ob.order.id}/payment/claim")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 409
    assert r.json()["detail"] == "payment_settled"


@pytest.mark.asyncio
async def test_claim_rejects_seller_acting_for_customer(
    approved_seller_with_store: Any, session: AsyncSession
) -> None:
    """A seller must not be able to fabricate the customer's assertion — that
    is the very claim the seller is supposed to be verifying independently."""
    from app.core.security import get_current_user

    bundle = approved_seller_with_store
    ob = await _make_order(session, bundle, method="upi")
    app.dependency_overrides[get_current_user] = lambda: bundle.user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(f"/api/v1/orders/{ob.order.id}/payment/claim")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 403


# ── Order-placed email UPI block ──────────────────────────────────────
def test_order_placed_email_renders_upi_block() -> None:
    """The emailed amount must be the NET payable, not the gross total."""
    from app.core.email_render import render_email

    payload = render_email(
        "order_placed_customer",
        {
            "orders": [
                {
                    "order_id": 42,
                    "service_name": "Grocery",
                    "store_name": "Ganesh Stores",
                    "line_items": [],
                    "order_total": 1247.50,
                    "subtotal": 1247.50,
                    "delivery_fee": 0.0,
                    "delivery_eta": None,
                    "preferred_delivery": None,
                    "upi_vpa": "ganesh@okhdfcbank",
                    "upi_payable": 1047.50,
                }
            ],
            "grand_total": 1247.50,
            "customer_first_name": "Asha",
        },
        lang="en",
    )
    assert "ganesh@okhdfcbank" in payload.html
    assert "1047.50" in payload.html
    # The gross must NOT be presented as the amount to transfer.
    assert "Pay ₹1247.50" not in payload.html


def test_order_placed_email_omits_upi_block_for_cash() -> None:
    from app.core.email_render import render_email

    payload = render_email(
        "order_placed_customer",
        {
            "orders": [
                {
                    "order_id": 43,
                    "service_name": "Grocery",
                    "store_name": "Ganesh Stores",
                    "line_items": [],
                    "order_total": 500.0,
                    "subtotal": 500.0,
                    "delivery_fee": 0.0,
                    "delivery_eta": None,
                    "preferred_delivery": None,
                    "upi_vpa": None,
                    "upi_payable": None,
                }
            ],
            "grand_total": 500.0,
            "customer_first_name": "Asha",
        },
        lang="en",
    )
    assert "by UPI" not in payload.html
