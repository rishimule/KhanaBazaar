# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import NotificationType
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeModel,
    ServiceFeeConfig,
    ServiceSubscriptionPlan,
)
from app.services.fee_notifications import notify_seller_fee_event
from app.services.notifications import list_notifications


@pytest.mark.asyncio
async def test_notify_records_seller_notification(
    session: AsyncSession, approved_seller_with_store
) -> None:
    await notify_seller_fee_event(
        session, store_id=approved_seller_with_store.store.id,
        type=NotificationType.FeeActivated, valid_until=date(2026, 10, 1),
    )
    await session.commit()
    items, unread = await list_notifications(
        session, seller_profile_id=approved_seller_with_store.profile.id
    )
    assert unread == 1
    assert items[0].type == NotificationType.FeeActivated
    assert "2026-10-01" in items[0].body  # valid_until surfaced in copy


@pytest.mark.asyncio
async def test_expiring_notification_names_the_consequence(
    session: AsyncSession, approved_seller_with_store
) -> None:
    # The seller UX audit (BLOCKER #3) found the real penalty — removal from
    # every customer surface — disclosed only in FAQ Q12. Dunning copy must say it.
    spid = await notify_seller_fee_event(
        session,
        store_id=approved_seller_with_store.store.id,
        type=NotificationType.FeeExpiring,
        valid_until=date(2026, 9, 1),
    )
    await session.commit()
    assert spid is not None
    items, _unread = await list_notifications(session, seller_profile_id=spid)
    assert items
    assert "2026-09-01" in items[0].body
    assert "find or order" in items[0].body
    # Expiry is not the cutoff — suspension is expiry + grace_period_days, so the
    # copy must not promise the penalty lands on the expiry date itself.
    assert "grace" in items[0].body


@pytest.mark.asyncio
async def test_suspended_and_overdue_notifications_name_the_consequence(
    session: AsyncSession, approved_seller_with_store
) -> None:
    # The other two dunning notices carry the same canonical penalty clause.
    for ntype in (
        NotificationType.FeeSuspended,
        NotificationType.FeeInvoiceOverdue,
    ):
        spid = await notify_seller_fee_event(
            session,
            store_id=approved_seller_with_store.store.id,
            type=ntype,
            valid_until=date(2026, 9, 1),
        )
        assert spid is not None
    await session.commit()
    items, _unread = await list_notifications(
        session, seller_profile_id=approved_seller_with_store.profile.id
    )
    bodies = {i.type: i.body for i in items}
    assert "find it or place an order" in bodies[NotificationType.FeeSuspended]
    assert "find or order" in bodies[NotificationType.FeeInvoiceOverdue]


@pytest.mark.asyncio
async def test_notify_noop_when_store_missing(session: AsyncSession) -> None:
    # Unresolvable store → silent no-op, no exception.
    await notify_seller_fee_event(
        session, store_id=999999, type=NotificationType.FeeSuspended
    )
    await session.commit()  # nothing recorded, no error


async def _enrolled(session, bundle):
    session.add(ServiceFeeConfig(service_id=bundle.service_id, subscription_enabled=True))
    session.add(ServiceSubscriptionPlan(service_id=bundle.service_id, duration_months=3, price=300.0, is_active=True))
    session.add(FeeArrangement(
        store_id=bundle.store.id, service_id=bundle.service_id,
        model=FeeModel.Freebie, status=ArrangementStatus.Trial, valid_until=None,
    ))
    await session.commit()


@pytest.mark.asyncio
async def test_confirm_notifies_seller(
    client, session: AsyncSession, approved_seller_with_store, admin_auth_headers
) -> None:
    from app import app
    from app.core.security import get_current_seller

    await _enrolled(session, approved_seller_with_store)
    sid = approved_seller_with_store.service_id
    # Persist a real admin (audit/confirm FK); seller opts in.
    from app.models.base import User, UserRole
    admin = User(id=99001, email="admin-test@kb.com", role=UserRole.Admin, is_active=True)
    session.add(admin)
    await session.commit()
    app.dependency_overrides[get_current_seller] = lambda: approved_seller_with_store.user
    try:
        await client.post(f"/api/v1/sellers/me/plan/{sid}/opt-in", json={"duration_months": 3})
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
    q = await client.get("/api/v1/admin/fees/queue", headers=admin_auth_headers)
    pid = next(i for i in q.json() if i["service_id"] == sid)["payment_id"]
    await client.post(f"/api/v1/admin/fees/payments/{pid}/confirm", headers=admin_auth_headers)
    _items, unread = await list_notifications(
        session, seller_profile_id=approved_seller_with_store.profile.id
    )
    assert unread >= 1  # seller got a FeeActivated notification


@pytest.mark.asyncio
async def test_sweep_reminds_before_expiry(
    session: AsyncSession, approved_seller_with_store
) -> None:
    from app.services.fee_lifecycle import run_fee_sweep

    session.add(ServiceFeeConfig(service_id=approved_seller_with_store.service_id, subscription_enabled=True))
    # Active subscription expiring in 3 days (within default 7-day reminder window).
    arr = FeeArrangement(
        store_id=approved_seller_with_store.store.id, service_id=approved_seller_with_store.service_id,
        model=FeeModel.Subscription, status=ArrangementStatus.Active,
        valid_until=date(2026, 7, 8),
    )
    session.add(arr)
    await session.flush()
    counts = await run_fee_sweep(session, today=date(2026, 7, 5))
    await session.commit()
    assert counts["reminded"] == 1
    await session.refresh(arr)
    assert arr.last_reminder_sent_on == date(2026, 7, 5)
    _items, unread = await list_notifications(
        session, seller_profile_id=approved_seller_with_store.profile.id
    )
    assert unread == 1  # FeeExpiring
    # Second sweep same day → throttled, no duplicate.
    counts2 = await run_fee_sweep(session, today=date(2026, 7, 5))
    assert counts2["reminded"] == 0


@pytest.mark.asyncio
async def test_sweep_suspend_notifies(
    session: AsyncSession, approved_seller_with_store
) -> None:
    from app.services.fee_lifecycle import run_fee_sweep

    # grace=0 default? Use an expired Active with a paid model so it suspends.
    session.add(ServiceFeeConfig(service_id=approved_seller_with_store.service_id, subscription_enabled=True))
    from app.models.platform_fee import PlatformFeeSettings
    session.add(PlatformFeeSettings(grace_period_days=0))
    arr = FeeArrangement(
        store_id=approved_seller_with_store.store.id, service_id=approved_seller_with_store.service_id,
        model=FeeModel.Subscription, status=ArrangementStatus.Active,
        valid_until=date(2026, 7, 1),
    )
    session.add(arr)
    await session.flush()
    counts = await run_fee_sweep(session, today=date(2026, 7, 10))
    await session.commit()
    assert counts["to_suspended"] == 1
    _items, unread = await list_notifications(
        session, seller_profile_id=approved_seller_with_store.profile.id
    )
    assert any(i.status_value == "suspended" for i in _items)
