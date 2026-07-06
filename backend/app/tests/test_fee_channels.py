# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from unittest.mock import patch

import pytest

from app.core.whatsapp_templates import FEE_TEMPLATES, TEMPLATES


def test_fee_templates_registered() -> None:
    for key in ("fee_activated", "fee_expiring", "fee_suspended"):
        assert key in TEMPLATES
        assert TEMPLATES[key].category == "UTILITY"
    # FEE_TEMPLATES keyed by NotificationType value.
    assert FEE_TEMPLATES["fee_expiring"].name == "fee_expiring"


def test_fee_expiring_render_includes_date() -> None:
    text = TEMPLATES["fee_expiring"].render({"until": "2026-10-01"})
    assert "2026-10-01" in text


def test_dispatch_enqueues_all_channels() -> None:
    from app.services import fee_channels

    with patch.object(fee_channels, "_safe_delay") as sd:
        fee_channels.dispatch_seller_fee_channels(1, "fee_activated", "2026-10-01")
    # SMS + WhatsApp + email → 3 enqueues.
    assert sd.call_count == 3


@pytest.mark.asyncio
async def test_confirm_dispatches_channels(
    client, session, approved_seller_with_store, admin_auth_headers
) -> None:
    from app import app
    from app.models.base import User, UserRole
    from app.models.platform_fee import (
        ArrangementStatus,
        FeeArrangement,
        FeeModel,
        ServiceFeeConfig,
        ServiceSubscriptionPlan,
    )

    session.add(ServiceFeeConfig(service_id=approved_seller_with_store.service_id, subscription_enabled=True))
    session.add(ServiceSubscriptionPlan(service_id=approved_seller_with_store.service_id, duration_months=3, price=300.0, is_active=True))
    session.add(FeeArrangement(store_id=approved_seller_with_store.store.id, service_id=approved_seller_with_store.service_id,
        model=FeeModel.Freebie, status=ArrangementStatus.Trial, valid_until=None))
    session.add(User(id=99001, email="admin-test@kb.com", role=UserRole.Admin, is_active=True))
    await session.commit()
    sid = approved_seller_with_store.service_id
    from app.core.security import get_current_seller
    app.dependency_overrides[get_current_seller] = lambda: approved_seller_with_store.user
    try:
        await client.post(f"/api/v1/sellers/me/plan/{sid}/opt-in", json={"duration_months": 3})
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
    pid = next(i for i in (await client.get("/api/v1/admin/fees/queue", headers=admin_auth_headers)).json()
               if i["service_id"] == sid)["payment_id"]
    with patch("app.api.platform_fees.dispatch_seller_fee_channels") as disp:
        await client.post(f"/api/v1/admin/fees/payments/{pid}/confirm", headers=admin_auth_headers)
    disp.assert_called_once()
    assert disp.call_args.args[1] == "fee_activated"
