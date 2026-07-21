# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""PPT fee deduction at order placement + refund on cancel (unit-level against
real Order rows). End-to-end checkout wiring is covered by the existing order
suite regression once the hooks are added."""
import uuid

import pytest
import pytest_asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.commerce import Order, OrderStatus
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeEvent,
    FeeEventType,
    FeeModel,
    ServiceFeeConfig,
)
from app.models.profile import CustomerProfile
from app.services.platform_txn import charge_platform_txn_fee, refund_platform_txn_fee
from tests._helpers import make_address


class _Env:
    def __init__(self, *, store, service_id, customer_profile_id, address_id):
        self.store = store
        self.service_id = service_id
        self.customer_profile_id = customer_profile_id
        self.address_id = address_id


@pytest_asyncio.fixture
async def ppt_env(session: AsyncSession, approved_seller_with_store) -> _Env:
    bundle = approved_seller_with_store
    user = User(email=f"c-{uuid.uuid4().hex[:8]}@x.test", role=UserRole.Customer)
    session.add(user)
    await session.flush()
    profile = CustomerProfile(user_id=user.id, first_name="Cust")
    session.add(profile)
    await session.flush()
    addr = Address(**make_address())
    session.add(addr)
    await session.flush()
    await session.commit()
    return _Env(
        store=bundle.store, service_id=bundle.service_id,
        customer_profile_id=profile.id, address_id=addr.id,
    )


async def _cfg(session: AsyncSession, service_id: int, *, fee: float) -> None:
    session.add(
        ServiceFeeConfig(
            service_id=service_id, pay_per_txn_enabled=True, pay_per_txn_fee=fee,
            pay_per_txn_low_balance_threshold=0.0,
        )
    )
    await session.flush()


async def _arr(session: AsyncSession, env: _Env, *, balance: float) -> FeeArrangement:
    arr = FeeArrangement(
        store_id=env.store.id, service_id=env.service_id,
        model=FeeModel.PayPerTransaction, status=ArrangementStatus.Active,
        balance=balance,
    )
    session.add(arr)
    await session.flush()
    return arr


async def _order(session: AsyncSession, env: _Env) -> Order:
    order = Order(
        customer_profile_id=env.customer_profile_id, store_id=env.store.id,
        service_id=env.service_id, service_name_snapshot="Grocery",
        delivery_address_id=env.address_id, status=OrderStatus.Pending,
        subtotal=100.0, delivery_fee=0.0, tax=0.0, total=100.0,
        delivery_address_snapshot="addr",
    )
    session.add(order)
    await session.flush()
    return order


@pytest.mark.asyncio
async def test_placing_order_deducts_fee(session, ppt_env):
    await _cfg(session, ppt_env.service_id, fee=2.0)
    arr = await _arr(session, ppt_env, balance=100.0)
    order = await _order(session, ppt_env)
    await charge_platform_txn_fee(session, order)
    await session.commit()
    await session.refresh(arr)
    assert arr.balance == 98.0
    ev = (
        await session.exec(
            select(FeeEvent).where(
                FeeEvent.order_id == order.id,
                FeeEvent.event_type == FeeEventType.BalanceDeducted,
            )
        )
    ).first()
    assert ev is not None and ev.amount_delta == -2.0


@pytest.mark.asyncio
async def test_last_affordable_order_moves_to_grace(session, ppt_env):
    await _cfg(session, ppt_env.service_id, fee=2.0)
    arr = await _arr(session, ppt_env, balance=3.0)
    order = await _order(session, ppt_env)
    await charge_platform_txn_fee(session, order)
    await session.commit()
    await session.refresh(arr)
    assert arr.balance == 1.0
    assert arr.status == ArrangementStatus.Grace  # 1.0 < fee 2.0


@pytest.mark.asyncio
async def test_zero_fee_no_deduction(session, ppt_env):
    await _cfg(session, ppt_env.service_id, fee=0.0)
    arr = await _arr(session, ppt_env, balance=100.0)
    order = await _order(session, ppt_env)
    await charge_platform_txn_fee(session, order)
    await session.commit()
    await session.refresh(arr)
    assert arr.balance == 100.0 and arr.status == ArrangementStatus.Active


@pytest.mark.asyncio
async def test_cancel_refunds_fee(session, ppt_env):
    await _cfg(session, ppt_env.service_id, fee=2.0)
    arr = await _arr(session, ppt_env, balance=100.0)
    order = await _order(session, ppt_env)
    await charge_platform_txn_fee(session, order)
    await session.commit()
    await refund_platform_txn_fee(session, order)
    await session.commit()
    await session.refresh(arr)
    assert arr.balance == 100.0  # 98 after charge, +2 refunded


@pytest.mark.asyncio
async def test_refund_is_idempotent(session, ppt_env):
    await _cfg(session, ppt_env.service_id, fee=2.0)
    arr = await _arr(session, ppt_env, balance=100.0)
    order = await _order(session, ppt_env)
    await charge_platform_txn_fee(session, order)
    await session.commit()
    await refund_platform_txn_fee(session, order)
    await refund_platform_txn_fee(session, order)  # second attempt
    await session.commit()
    await session.refresh(arr)
    assert arr.balance == 100.0  # not 102


@pytest.mark.asyncio
async def test_no_arrangement_is_noop(session, ppt_env):
    # No PPT arrangement for this (store, service): charge is a silent no-op.
    order = await _order(session, ppt_env)
    await charge_platform_txn_fee(session, order)
    await session.commit()
    events = (await session.exec(select(FeeEvent).where(FeeEvent.order_id == order.id))).all()
    assert events == []
