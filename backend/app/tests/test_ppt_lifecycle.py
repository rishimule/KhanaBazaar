# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pay-Per-Transaction lifecycle: opt-in, balance evaluator, confirm/top-up,
apply-credit, exit/model-switch, and notification copy."""
from datetime import date

import pytest
import pytest_asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import Notification, NotificationType
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeModel,
    FeePayment,
    FeePaymentKind,
    FeePaymentStatus,
    ServiceFeeConfig,
)
from app.models.store import Store
from app.services import fee_lifecycle as fl
from app.services import store_credit


@pytest_asyncio.fixture
async def seeded_store_with_service(approved_seller_with_store):
    """(live Store, service_id) for an approved seller offering one service."""
    bundle = approved_seller_with_store
    return bundle.store, bundle.service_id


async def _cfg(
    session: AsyncSession, service_id: int, *, fee=2.0, min_deposit=100.0, low=10.0
) -> ServiceFeeConfig:
    cfg = ServiceFeeConfig(
        service_id=service_id, pay_per_txn_enabled=True, pay_per_txn_fee=fee,
        pay_per_txn_min_deposit=min_deposit, pay_per_txn_low_balance_threshold=low,
    )
    session.add(cfg)
    await session.flush()
    return cfg


async def _ppt_arr(
    session: AsyncSession, store, service_id: int, *,
    status=ArrangementStatus.PendingActivation, balance=0.0, valid_until=None,
) -> FeeArrangement:
    arr = FeeArrangement(
        store_id=store.id, service_id=service_id, model=FeeModel.PayPerTransaction,
        status=status, balance=balance, valid_until=valid_until,
    )
    session.add(arr)
    await session.flush()
    return arr


# ── Task 3: opt-in + evaluator ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_opt_in_cash_creates_pending_payment(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id)
    arr = await _ppt_arr(session, store, service_id)
    payment = await fl.opt_into_pay_per_transaction(session, arr, 100.0)
    await session.commit()
    assert payment is not None
    assert payment.kind == FeePaymentKind.PayPerTxnTopUp
    assert payment.amount == 100.0
    assert arr.status == ArrangementStatus.PendingActivation


@pytest.mark.asyncio
async def test_opt_in_below_min_deposit_rejected(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, min_deposit=100.0)
    arr = await _ppt_arr(session, store, service_id)
    with pytest.raises(fl.FeeError):
        await fl.opt_into_pay_per_transaction(session, arr, 50.0)


@pytest.mark.asyncio
async def test_opt_in_full_credit_activates_without_payment(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, min_deposit=100.0)
    await store_credit.grant(session, store, 120.0, actor="admin:1")
    arr = await _ppt_arr(session, store, service_id)
    payment = await fl.opt_into_pay_per_transaction(session, arr, 100.0, use_credit=True)
    await session.commit()
    assert payment is None
    assert arr.status == ArrangementStatus.Active
    assert arr.balance == 100.0
    assert (await session.get(Store, store.id)).fee_credit_balance == 20.0


@pytest.mark.asyncio
async def test_evaluate_active_to_grace(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, fee=2.0, low=10.0)
    arr = await _ppt_arr(session, store, service_id, status=ArrangementStatus.Active, balance=1.0)
    await fl._evaluate_ppt_status(session, arr, today=date(2026, 7, 21))
    assert arr.status == ArrangementStatus.Grace
    assert arr.valid_until == date(2026, 7, 21)


@pytest.mark.asyncio
async def test_evaluate_grace_to_active_on_refill(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, fee=2.0)
    arr = await _ppt_arr(session, store, service_id, status=ArrangementStatus.Grace, balance=50.0, valid_until=date(2026, 7, 21))
    await fl._evaluate_ppt_status(session, arr, today=date(2026, 7, 22))
    assert arr.status == ArrangementStatus.Active
    assert arr.valid_until is None


# ── Task 4: confirm top-up / activation ────────────────────────────────────

@pytest.mark.asyncio
async def test_confirm_topup_activates(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, fee=2.0, min_deposit=100.0)
    arr = await _ppt_arr(session, store, service_id)
    payment = await fl.opt_into_pay_per_transaction(session, arr, 100.0)
    await session.commit()
    activated, notif = await fl.confirm_pay_per_txn_topup(session, payment, admin_user_id=1)
    await session.commit()
    assert activated.status == ArrangementStatus.Active
    assert activated.balance == 100.0
    # Fresh activation → FeeActivated (not FeeReactivated).
    assert notif == NotificationType.FeeActivated


@pytest.mark.asyncio
async def test_confirm_topup_reactivates_suspended(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, fee=2.0)
    arr = await _ppt_arr(session, store, service_id, status=ArrangementStatus.Suspended, balance=-4.0, valid_until=date(2026, 7, 1))
    payment = FeePayment(arrangement_id=arr.id, kind=FeePaymentKind.PayPerTxnTopUp, amount=50.0, status=FeePaymentStatus.Pending)
    session.add(payment)
    await session.commit()
    _arr, notif = await fl.confirm_pay_per_txn_topup(session, payment, admin_user_id=1)
    await session.commit()
    await session.refresh(arr)
    assert arr.status == ArrangementStatus.Active
    assert arr.balance == 46.0
    assert arr.valid_until is None
    # Reactivating top-up → FeeReactivated (recorded once, inside the service).
    assert notif == NotificationType.FeeReactivated


# ── Task 5: cash top-up + instant apply-credit ─────────────────────────────

@pytest.mark.asyncio
async def test_apply_credit_reactivates_grace(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, fee=2.0)
    await store_credit.grant(session, store, 30.0, actor="admin:1")
    arr = await _ppt_arr(session, store, service_id, status=ArrangementStatus.Grace, balance=0.5, valid_until=date(2026, 7, 21))
    applied = await fl.apply_credit_to_arrangement(session, arr, 20.0)
    await session.commit()
    await session.refresh(arr)
    assert applied == 20.0
    assert arr.balance == 20.5
    assert arr.status == ArrangementStatus.Active


@pytest.mark.asyncio
async def test_create_top_up_pending(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id)
    arr = await _ppt_arr(session, store, service_id, status=ArrangementStatus.Active, balance=50.0)
    payment = await fl.create_top_up(session, arr, 100.0)
    await session.commit()
    assert payment.kind == FeePaymentKind.PayPerTxnTopUp
    assert payment.status == FeePaymentStatus.Pending


# ── Task 7: exit / model-switch ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seller_switch_blocked_on_negative(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, fee=2.0)
    arr = await _ppt_arr(session, store, service_id, status=ArrangementStatus.Grace, balance=-3.0, valid_until=date(2026, 7, 21))
    with pytest.raises(fl.FeeError):
        await fl.seller_switch_from_ppt(session, arr)


@pytest.mark.asyncio
async def test_seller_switch_positive_to_credit(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, fee=2.0)
    arr = await _ppt_arr(session, store, service_id, status=ArrangementStatus.Active, balance=40.0)
    await fl.seller_switch_from_ppt(session, arr)
    await session.commit()
    assert (await session.get(Store, store.id)).fee_credit_balance == 40.0
    assert arr.balance == 0.0


@pytest.mark.asyncio
async def test_admin_switch_negative_waive(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    cfg = await _cfg(session, service_id, fee=2.0)
    cfg.freebie_default_days = 30
    session.add(cfg)
    arr = await _ppt_arr(session, store, service_id, status=ArrangementStatus.Grace, balance=-5.0, valid_until=date(2026, 7, 21))
    await fl.admin_switch_model(session, arr, target_model=FeeModel.Freebie, disposition="waive", admin_user_id=1)
    await session.commit()
    await session.refresh(arr)
    assert arr.model == FeeModel.Freebie
    assert arr.status == ArrangementStatus.Trial
    assert arr.balance == 0.0
    # Waiving a debt must NOT mint spendable wallet credit (money-neutral).
    assert (await session.get(Store, store.id)).fee_credit_balance == 0.0


@pytest.mark.asyncio
async def test_admin_switch_positive_credit_disposition(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    cfg = await _cfg(session, service_id, fee=2.0)
    cfg.freebie_default_days = 30
    session.add(cfg)
    arr = await _ppt_arr(session, store, service_id, status=ArrangementStatus.Active, balance=40.0)
    await fl.admin_switch_model(session, arr, target_model=FeeModel.Freebie, disposition="credit", admin_user_id=1)
    await session.commit()
    await session.refresh(arr)
    assert arr.balance == 0.0
    # Positive balance → store wallet credit.
    assert (await session.get(Store, store.id)).fee_credit_balance == 40.0


@pytest.mark.asyncio
async def test_admin_switch_positive_cash_out_disposition(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    cfg = await _cfg(session, service_id, fee=2.0)
    cfg.freebie_default_days = 30
    session.add(cfg)
    arr = await _ppt_arr(session, store, service_id, status=ArrangementStatus.Active, balance=40.0)
    await fl.admin_switch_model(session, arr, target_model=FeeModel.Freebie, disposition="cash_out", admin_user_id=1)
    await session.commit()
    await session.refresh(arr)
    assert arr.balance == 0.0
    # cash_out = grant(+40) then cash_out(-40): net-zero wallet, refund recorded.
    assert (await session.get(Store, store.id)).fee_credit_balance == 0.0


# ── Task 12: notification copy ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_low_balance_notification_recorded(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, fee=2.0, low=10.0)
    arr = await _ppt_arr(session, store, service_id, status=ArrangementStatus.Active, balance=5.0)
    await fl._evaluate_ppt_status(session, arr, today=date(2026, 7, 21))
    await session.commit()
    notifs = (
        await session.exec(
            select(Notification).where(Notification.type == NotificationType.FeeLowBalance)
        )
    ).all()
    assert len(notifs) == 1
