# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.admin_audit import AdminActionLog
from app.models.commerce import Delivery
from app.models.notification import Notification, NotificationType

# Reuse the full order-test harness (seed fixture, mock users, helpers).
from tests.test_orders import (  # noqa: F401
    _order_id_for_store,
    _place_orders,
    as_customer,
    mock_admin,
    mock_customer,
    mock_other_customer,
    mock_seller,
    seed,
)


async def _packed_then_dispatched(ac: AsyncClient, order_id: int) -> None:
    await ac.post(f"/api/v1/orders/{order_id}/transition", json={"to": "packed"})
    await ac.post(f"/api/v1/orders/{order_id}/transition", json={"to": "dispatched"})


async def _read_code(order_id: int) -> str | None:
    from tests.conftest import test_engine

    async with AsyncSession(test_engine) as s:
        return (
            await s.exec(
                select(Delivery.delivery_otp).where(Delivery.order_id == order_id)
            )
        ).first()


async def test_dispatch_generates_code_and_records_notification(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await _packed_then_dispatched(ac, target)

    code = await _read_code(target)
    assert code is not None and len(code) == 6

    notif = (
        await session.exec(
            select(Notification).where(
                Notification.order_id == target,
                Notification.type == NotificationType.DeliveryOtp,
            )
        )
    ).first()
    assert notif is not None
    assert code in notif.body


async def test_seller_cannot_deliver_without_otp(
    as_customer: Any, seed: dict[str, int]
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await _packed_then_dispatched(ac, target)
        resp = await ac.post(
            f"/api/v1/orders/{target}/transition", json={"to": "delivered"}
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "delivery_otp_required"


async def test_wrong_otp_increments_then_locks(
    as_customer: Any, seed: dict[str, int]
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await _packed_then_dispatched(ac, target)
        # First wrong attempt reports the remaining countdown (5 → 4).
        first = await ac.post(
            f"/api/v1/orders/{target}/transition",
            json={"to": "delivered", "otp": "000000"},
        )
        assert first.status_code == 422
        assert first.json()["detail"]["code"] == "delivery_otp_invalid"
        assert first.json()["detail"]["remaining"] == 4
        # Exhaust the rest of the cap (DELIVERY_OTP_MAX_ATTEMPTS default 5).
        last = first
        for _ in range(4):
            last = await ac.post(
                f"/api/v1/orders/{target}/transition",
                json={"to": "delivered", "otp": "000000"},
            )
        assert last.status_code == 422
        assert last.json()["detail"]["code"] == "delivery_otp_invalid"
        # Seller read surfaces lock state (but never the code).
        seller_view = await ac.get(f"/api/v1/orders/{target}")
        assert seller_view.json()["delivery"]["otp"] is None
        assert seller_view.json()["delivery"]["otp_locked"] is True
        assert seller_view.json()["delivery"]["otp_attempts_remaining"] == 0
        # 6th attempt → locked.
        locked = await ac.post(
            f"/api/v1/orders/{target}/transition",
            json={"to": "delivered", "otp": "000000"},
        )
    assert locked.status_code == 409
    assert locked.json()["detail"]["code"] == "delivery_otp_locked"


async def test_correct_otp_delivers_and_clears_code(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await _packed_then_dispatched(ac, target)
        code = await _read_code(target)
        resp = await ac.post(
            f"/api/v1/orders/{target}/transition",
            json={"to": "delivered", "otp": code},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "delivered"
    assert resp.json()["payment"]["status"] == "paid"

    delivery = (
        await session.exec(select(Delivery).where(Delivery.order_id == target))
    ).first()
    assert delivery is not None
    assert delivery.delivery_otp is None
    assert delivery.delivery_otp_verified_at is not None


async def test_resend_resets_attempts(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await _packed_then_dispatched(ac, target)
        await ac.post(
            f"/api/v1/orders/{target}/transition",
            json={"to": "delivered", "otp": "000000"},
        )
    code = await _read_code(target)

    # Resend within the cooldown window is rejected.
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        too_soon = await ac.post(f"/api/v1/orders/{target}/delivery-otp/resend")
    assert too_soon.status_code == 429
    assert too_soon.json()["detail"]["code"] == "resend_cooldown"
    assert too_soon.json()["detail"]["retry_after"] > 0

    # Backdate sent_at past the cooldown, then resend succeeds.
    from datetime import datetime, timedelta, timezone

    from tests.conftest import test_engine

    async with AsyncSession(test_engine) as s:
        d = (
            await s.exec(select(Delivery).where(Delivery.order_id == target))
        ).first()
        assert d is not None
        d.delivery_otp_sent_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        s.add(d)
        await s.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resend = await ac.post(f"/api/v1/orders/{target}/delivery-otp/resend")
    assert resend.status_code == 200

    delivery = (
        await session.exec(select(Delivery).where(Delivery.order_id == target))
    ).first()
    assert delivery is not None
    assert delivery.delivery_otp_attempts == 0
    assert delivery.delivery_otp == code  # same code re-sent


async def test_resend_rejected_when_not_dispatched(
    as_customer: Any, seed: dict[str, int]
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_customer
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(f"/api/v1/orders/{target}/delivery-otp/resend")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "not_dispatched"


async def test_admin_force_deliver_requires_reason(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await _packed_then_dispatched(ac, target)

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        no_reason = await ac.post(
            f"/api/v1/orders/{target}/transition", json={"to": "delivered"}
        )
        assert no_reason.status_code == 422
        assert no_reason.json()["detail"]["code"] == "reason_required"
        ok = await ac.post(
            f"/api/v1/orders/{target}/transition",
            json={"to": "delivered", "reason": "customer unreachable at door"},
        )
    assert ok.status_code == 200
    assert ok.json()["status"] == "delivered"

    # Force-deliver writes a distinct audit action carrying the reason.
    row = (
        await session.exec(
            select(AdminActionLog).where(
                AdminActionLog.action == "order.force_deliver",
                AdminActionLog.target_id == target,
            )
        )
    ).first()
    assert row is not None
    assert row.reason == "customer unreachable at door"


async def test_other_customer_cannot_read_or_resend_otp(
    as_customer: Any, seed: dict[str, int]
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await _packed_then_dispatched(ac, target)

    # A different customer may neither read the code nor resend it.
    app.dependency_overrides[get_current_user] = lambda: mock_other_customer
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        read = await ac.get(f"/api/v1/orders/{target}")
        resend = await ac.post(f"/api/v1/orders/{target}/delivery-otp/resend")
    assert read.status_code == 403
    assert resend.status_code == 403


async def test_admin_sees_otp_and_can_resend_seller_cannot(
    as_customer: Any, seed: dict[str, int]
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await _packed_then_dispatched(ac, target)
        # Seller never sees the code and may not resend it.
        seller_view = await ac.get(f"/api/v1/orders/{target}")
        seller_resend = await ac.post(f"/api/v1/orders/{target}/delivery-otp/resend")
    assert seller_view.json()["delivery"]["otp"] is None
    assert seller_resend.status_code == 403

    code = await _read_code(target)

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        admin_view = await ac.get(f"/api/v1/orders/{target}")
    assert admin_view.json()["delivery"]["otp"] == code

    # Admin resend is allowed (past the role gate); backdate to clear cooldown.
    from datetime import datetime, timedelta, timezone

    from tests.conftest import test_engine

    async with AsyncSession(test_engine) as s:
        d = (
            await s.exec(select(Delivery).where(Delivery.order_id == target))
        ).first()
        assert d is not None
        d.delivery_otp_sent_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        s.add(d)
        await s.commit()

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        admin_resend = await ac.post(f"/api/v1/orders/{target}/delivery-otp/resend")
    assert admin_resend.status_code == 200
    assert admin_resend.json()["delivery"]["otp"] == code


async def test_customer_sees_code_seller_does_not(
    as_customer: Any, seed: dict[str, int]
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])

    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await _packed_then_dispatched(ac, target)
        seller_view = await ac.get(f"/api/v1/orders/{target}")
    assert seller_view.json()["delivery"]["otp"] is None

    app.dependency_overrides[get_current_user] = lambda: mock_customer
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        cust_view = await ac.get(f"/api/v1/orders/{target}")
    otp = cust_view.json()["delivery"]["otp"]
    assert otp is not None and len(otp) == 6
