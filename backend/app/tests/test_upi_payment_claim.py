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
