# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.admin_audit import AdminActionLog
from app.models.base import User
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from tests._returns_helpers import (
    as_admin,
    as_customer,
    as_seller,
    clear_overrides,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def test_seller_sets_the_window(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, return_window_days=3)
    as_seller(seed.seller_user)

    resp = await client.patch(
        f"/api/v1/sellers/me/services/{seed.service_id}/returns",
        json={"return_window_days": 7},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["return_window_days"] == 7

    session.expunge_all()
    row = (await session.exec(
        select(SellerProfileService).where(
            SellerProfileService.seller_profile_id == seed.seller_profile_id
        )
    )).first()
    assert row is not None
    assert row.return_window_days == 7


async def test_approved_seller_is_not_blocked(
    session: AsyncSession, client: AsyncClient
) -> None:
    """The whole reason this has its own route: PATCH /me/services/{id}
    rejects approved sellers with `use_change_request`."""
    seed = await seed_delivered_order(session)
    profile = await session.get(SellerProfile, seed.seller_profile_id)
    assert profile is not None
    assert profile.verification_status == VerificationStatus.Approved
    as_seller(seed.seller_user)

    resp = await client.patch(
        f"/api/v1/sellers/me/services/{seed.service_id}/returns",
        json={"return_window_days": 10},
    )
    assert resp.status_code == 200
    assert resp.json()["return_window_days"] == 10


async def test_zero_disables_returns(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, return_window_days=7)
    as_seller(seed.seller_user)
    await client.patch(
        f"/api/v1/sellers/me/services/{seed.service_id}/returns",
        json={"return_window_days": 0},
    )

    as_customer(seed.customer_user)
    body = (await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")).json()
    assert body["eligible"] is False
    assert body["reason_code"] == "returns_disabled_for_service"


async def test_negative_is_rejected(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    as_seller(seed.seller_user)
    resp = await client.patch(
        f"/api/v1/sellers/me/services/{seed.service_id}/returns",
        json={"return_window_days": -1},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "invalid_return_window"


async def test_window_over_a_year_is_rejected(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    as_seller(seed.seller_user)
    resp = await client.patch(
        f"/api/v1/sellers/me/services/{seed.service_id}/returns",
        json={"return_window_days": 400},
    )
    assert resp.status_code == 422


async def test_unknown_service_is_404(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    as_seller(seed.seller_user)
    resp = await client.patch(
        "/api/v1/sellers/me/services/99999/returns", json={"return_window_days": 5}
    )
    assert resp.status_code == 404


async def test_admin_sets_the_window_and_audits(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    seed = await seed_delivered_order(session)
    as_admin(admin_user)

    resp = await client.patch(
        f"/api/v1/sellers/admin/{seed.seller_user_id}/services/{seed.service_id}/returns",
        json={"return_window_days": 14},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["return_window_days"] == 14

    logs = (await session.exec(select(AdminActionLog))).all()
    assert len(logs) == 1
    assert logs[0].action == "service.set_return_window"
    assert logs[0].before_json == {
        "service_id": seed.service_id, "return_window_days": 7
    }
    assert logs[0].after_json == {
        "service_id": seed.service_id, "return_window_days": 14
    }


async def test_admin_route_refuses_a_non_approved_seller(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    seed = await seed_delivered_order(session)
    profile = await session.get(SellerProfile, seed.seller_profile_id)
    assert profile is not None
    profile.verification_status = VerificationStatus.Pending
    session.add(profile)
    await session.commit()
    as_admin(admin_user)

    resp = await client.patch(
        f"/api/v1/sellers/admin/{seed.seller_user_id}/services/{seed.service_id}/returns",
        json={"return_window_days": 14},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "seller_not_active"
