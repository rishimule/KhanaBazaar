# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""PPT API: seller opt-in/top-up/apply-credit/switch + plan view; admin confirm
branch, force-switch, and wallet-credit control."""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_seller, get_current_user
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeModel,
    FeePayment,
    FeePaymentKind,
    FeePaymentStatus,
    ServiceFeeConfig,
)


async def _ppt_cfg(session: AsyncSession, service_id: int, *, fee=2.0, min_deposit=100.0, low=10.0) -> None:
    session.add(
        ServiceFeeConfig(
            service_id=service_id, pay_per_txn_enabled=True, pay_per_txn_fee=fee,
            pay_per_txn_min_deposit=min_deposit, pay_per_txn_low_balance_threshold=low,
            freebie_default_days=30,
        )
    )
    await session.commit()


async def _arr(session, store, service_id, *, model=FeeModel.Freebie,
               status=ArrangementStatus.Trial, balance=0.0, valid_until=None) -> FeeArrangement:
    arr = FeeArrangement(
        store_id=store.id, service_id=service_id, model=model, status=status,
        balance=balance, valid_until=valid_until,
    )
    session.add(arr)
    await session.commit()
    await session.refresh(arr)
    return arr


@pytest_asyncio.fixture
async def admin_ctx(session: AsyncSession, admin_user):
    """Override auth with a REAL persisted admin User (its id satisfies the
    confirmed_by_admin_id / admin_action_log FKs that these endpoints write)."""
    from app.core.security import get_current_admin
    app.dependency_overrides[get_current_admin] = lambda: admin_user
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        yield admin_user
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def ppt_seller(session: AsyncSession, approved_seller_with_store):
    """Approved seller (store + service) with PPT enabled + auth override."""
    bundle = approved_seller_with_store
    await _ppt_cfg(session, bundle.service_id)
    app.dependency_overrides[get_current_seller] = lambda: bundle.user
    app.dependency_overrides[get_current_user] = lambda: bundle.user
    try:
        yield bundle
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
        app.dependency_overrides.pop(get_current_user, None)


# ── Seller endpoints ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seller_opt_in_ppt(client: AsyncClient, session, ppt_seller):
    await _arr(session, ppt_seller.store, ppt_seller.service_id)  # freebie trial exists
    r = await client.post(
        f"/api/v1/sellers/me/plan/{ppt_seller.service_id}/pay-per-transaction/opt-in",
        json={"deposit_amount": 100.0},
    )
    assert r.status_code == 200, r.text
    assert r.json()["payment_id"] is not None


@pytest.mark.asyncio
async def test_seller_opt_in_below_min_400(client: AsyncClient, session, ppt_seller):
    await _arr(session, ppt_seller.store, ppt_seller.service_id)
    r = await client.post(
        f"/api/v1/sellers/me/plan/{ppt_seller.service_id}/pay-per-transaction/opt-in",
        json={"deposit_amount": 50.0},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "below_min_deposit"


@pytest.mark.asyncio
async def test_seller_switch_negative_blocked(client: AsyncClient, session, ppt_seller):
    await _arr(
        session, ppt_seller.store, ppt_seller.service_id,
        model=FeeModel.PayPerTransaction, status=ArrangementStatus.Grace,
        balance=-3.0, valid_until=None,
    )
    r = await client.post(f"/api/v1/sellers/me/plan/{ppt_seller.service_id}/switch")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "balance_negative"


@pytest.mark.asyncio
async def test_plan_view_exposes_balance(client: AsyncClient, session, ppt_seller):
    await _arr(
        session, ppt_seller.store, ppt_seller.service_id,
        model=FeeModel.PayPerTransaction, status=ArrangementStatus.Active, balance=50.0,
    )
    r = await client.get("/api/v1/sellers/me/plan")
    assert r.status_code == 200, r.text
    body = r.json()
    svc = next(s for s in body["services"] if s["service_id"] == ppt_seller.service_id)
    assert svc["balance"] == 50.0
    assert svc["pay_per_txn_enabled"] is True
    assert "fee_credit_balance" in body


# ── Admin endpoints ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_confirm_ppt_topup(client: AsyncClient, session, admin_ctx, approved_seller_with_store):
    bundle = approved_seller_with_store
    await _ppt_cfg(session, bundle.service_id)
    arr = await _arr(
        session, bundle.store, bundle.service_id,
        model=FeeModel.PayPerTransaction, status=ArrangementStatus.PendingActivation,
    )
    payment = FeePayment(
        arrangement_id=arr.id, kind=FeePaymentKind.PayPerTxnTopUp, amount=100.0,
        status=FeePaymentStatus.Pending,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    r = await client.post(f"/api/v1/admin/fees/payments/{payment.id}/confirm")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"


@pytest.mark.asyncio
async def test_admin_grant_credit(client: AsyncClient, session, admin_ctx, approved_seller_with_store):
    bundle = approved_seller_with_store
    r = await client.post(
        f"/api/v1/admin/fees/stores/{bundle.store.id}/credit/grant",
        json={"amount": 50.0, "reason": "goodwill credit for the outage last week"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["fee_credit_balance"] == 50.0


@pytest.mark.asyncio
async def test_admin_grant_credit_short_reason_422(client: AsyncClient, admin_ctx, approved_seller_with_store):
    bundle = approved_seller_with_store
    r = await client.post(
        f"/api/v1/admin/fees/stores/{bundle.store.id}/credit/grant",
        json={"amount": 50.0, "reason": "short"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_admin_force_switch_negative_waive(client: AsyncClient, session, admin_ctx, approved_seller_with_store):
    bundle = approved_seller_with_store
    await _ppt_cfg(session, bundle.service_id)
    arr = await _arr(
        session, bundle.store, bundle.service_id,
        model=FeeModel.PayPerTransaction, status=ArrangementStatus.Grace,
        balance=-5.0, valid_until=None,
    )
    r = await client.post(
        f"/api/v1/admin/fees/arrangements/{arr.id}/switch",
        json={"target_model": "freebie", "disposition": "waive", "reason": "moving seller to freebie plan"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["model"] == "freebie"


@pytest.mark.asyncio
async def test_admin_list_credit(client: AsyncClient, session, admin_ctx, approved_seller_with_store):
    bundle = approved_seller_with_store
    bundle.store.fee_credit_balance = 25.0
    session.add(bundle.store)
    await session.commit()
    r = await client.get("/api/v1/admin/fees/stores/credit")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert any(row["store_id"] == bundle.store.id and row["fee_credit_balance"] == 25.0 for row in rows)
