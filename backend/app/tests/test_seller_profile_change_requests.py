# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from __future__ import annotations

from typing import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlmodel import select

from app import app
from app.core.security import (
    get_current_admin,
    get_current_seller,
    get_current_user,
)
from app.models.base import User
from app.models.seller_profile_change_request import (
    SellerProfileChangeGroup,
    SellerProfileChangeRequestEvent,
    SellerProfileChangeStatus,
)
from app.services.seller_profile_change_requests import (
    create_change_request,
)


@pytest.mark.asyncio
async def test_create_cr_happy_path(approved_seller, session):
    profile = approved_seller["profile"]
    payload = {
        "bank_account_number": "123456789012",
        "bank_ifsc": "HDFC0001234",
    }
    result = await create_change_request(
        session=session,
        seller_profile=profile,
        group=SellerProfileChangeGroup.Banking,
        proposed=payload,
        note="please review",
        actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    cr = result.cr
    assert cr.status is SellerProfileChangeStatus.Submitted
    assert cr.submission_count == 1
    assert cr.proposed_json == payload
    assert "bank_account_number" in cr.baseline_json
    events = (
        await session.exec(
            select(SellerProfileChangeRequestEvent).where(
                SellerProfileChangeRequestEvent.change_request_id == cr.id
            )
        )
    ).all()
    assert len(events) == 1
    assert events[0].kind.value == "submitted"


@pytest.mark.asyncio
async def test_create_cr_blocks_when_seller_not_approved(pending_seller, session):
    from fastapi import HTTPException
    profile = pending_seller["profile"]
    with pytest.raises(HTTPException) as excinfo:
        await create_change_request(
            session=session,
            seller_profile=profile,
            group=SellerProfileChangeGroup.Banking,
            proposed={"bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234"},
            note=None,
            actor_user_id=pending_seller["user"].id,
        )
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "seller_not_active"


@pytest.mark.asyncio
async def test_create_cr_duplicate_group_blocks(approved_seller, session):
    from fastapi import HTTPException
    profile = approved_seller["profile"]
    await create_change_request(
        session=session,
        seller_profile=profile,
        group=SellerProfileChangeGroup.Banking,
        proposed={"bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234"},
        note=None,
        actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    with pytest.raises(HTTPException) as excinfo:
        await create_change_request(
            session=session,
            seller_profile=profile,
            group=SellerProfileChangeGroup.Banking,
            proposed={"bank_account_number": "999988887777", "bank_ifsc": "ICIC0009999"},
            note=None,
            actor_user_id=approved_seller["user"].id,
        )
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "cr_already_open"


@pytest.mark.asyncio
async def test_withdraw_open_cr(approved_seller, session):
    from app.services.seller_profile_change_requests import (
        create_change_request,
        withdraw,
    )
    profile = approved_seller["profile"]
    create = await create_change_request(
        session=session, seller_profile=profile,
        group=SellerProfileChangeGroup.Banking,
        proposed={"bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234"},
        note=None, actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    res = await withdraw(
        session=session, cr=create.cr,
        actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    assert res.cr.status is SellerProfileChangeStatus.Withdrawn
    assert res.cr.decided_at is not None
    # partial-unique index now allows fresh CR
    create2 = await create_change_request(
        session=session, seller_profile=profile,
        group=SellerProfileChangeGroup.Banking,
        proposed={"bank_account_number": "555566667777", "bank_ifsc": "ICIC0001234"},
        note=None, actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    assert create2.cr.id != create.cr.id


@pytest.mark.asyncio
async def test_resubmit_blocked_when_not_changes_requested(approved_seller, session):
    from fastapi import HTTPException

    from app.services.seller_profile_change_requests import (
        create_change_request,
        resubmit,
    )
    profile = approved_seller["profile"]
    create = await create_change_request(
        session=session, seller_profile=profile,
        group=SellerProfileChangeGroup.Banking,
        proposed={"bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234"},
        note=None, actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    with pytest.raises(HTTPException) as excinfo:
        await resubmit(
            session=session, cr=create.cr,
            proposed={"bank_account_number": "123456789012", "bank_ifsc": "ICIC0009999"},
            note=None, actor_user_id=approved_seller["user"].id,
        )
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "cr_not_resubmittable"


@pytest.mark.asyncio
async def test_resubmit_after_changes_requested(approved_seller, session, admin_user):
    from app.services.seller_profile_change_requests import (
        create_change_request,
        request_changes,
        resubmit,
    )
    profile = approved_seller["profile"]
    create = await create_change_request(
        session=session, seller_profile=profile,
        group=SellerProfileChangeGroup.Banking,
        proposed={"bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234"},
        note=None, actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    await request_changes(
        session=session, cr=create.cr,
        admin_user_id=admin_user.id, note="fix ifsc",
    )
    await session.commit()
    res = await resubmit(
        session=session, cr=create.cr,
        proposed={"bank_account_number": "123456789012", "bank_ifsc": "HDFC0009999"},
        note="fixed", actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    assert res.cr.status is SellerProfileChangeStatus.Submitted
    assert res.cr.submission_count == 2
    assert res.cr.proposed_json["bank_ifsc"] == "HDFC0009999"


@pytest.mark.asyncio
async def test_request_changes_writes_event_and_audit(approved_seller, session, admin_user):
    from app.models.admin_audit import AdminActionLog
    from app.services.seller_profile_change_requests import (
        create_change_request,
        request_changes,
    )
    profile = approved_seller["profile"]
    create = await create_change_request(
        session=session, seller_profile=profile,
        group=SellerProfileChangeGroup.Banking,
        proposed={"bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234"},
        note=None, actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    res = await request_changes(
        session=session, cr=create.cr,
        admin_user_id=admin_user.id, note="please correct IFSC",
    )
    await session.commit()
    assert res.cr.status is SellerProfileChangeStatus.ChangesRequested
    assert res.cr.admin_note == "please correct IFSC"
    rows = (
        await session.exec(select(AdminActionLog).where(
            AdminActionLog.action == "profile_cr_request_changes"
        ))
    ).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_reject_terminal(approved_seller, session, admin_user):
    from fastapi import HTTPException

    from app.services.seller_profile_change_requests import (
        create_change_request,
        reject,
        resubmit,
    )
    profile = approved_seller["profile"]
    create = await create_change_request(
        session=session, seller_profile=profile,
        group=SellerProfileChangeGroup.Banking,
        proposed={"bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234"},
        note=None, actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    await reject(
        session=session, cr=create.cr,
        admin_user_id=admin_user.id, reason="banking docs invalid",
    )
    await session.commit()
    assert create.cr.status is SellerProfileChangeStatus.Rejected
    with pytest.raises(HTTPException) as excinfo:
        await resubmit(
            session=session, cr=create.cr,
            proposed={"bank_account_number": "999988887777", "bank_ifsc": "ICIC0001234"},
            note=None, actor_user_id=approved_seller["user"].id,
        )
    assert excinfo.value.status_code == 409


@pytest.mark.asyncio
async def test_approve_no_edits_applies_proposed(approved_seller, session, admin_user):
    from app.models.admin_audit import AdminActionLog
    from app.services.seller_profile_change_requests import (
        approve,
        create_change_request,
    )
    profile = approved_seller["profile"]
    create = await create_change_request(
        session=session, seller_profile=profile,
        group=SellerProfileChangeGroup.Banking,
        proposed={"bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234"},
        note=None, actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    await approve(
        session=session, cr=create.cr,
        admin_user_id=admin_user.id, applied=None, note=None,
    )
    await session.commit()
    await session.refresh(profile)
    assert profile.bank_account_number == "123456789012"
    assert profile.bank_ifsc == "HDFC0001234"
    assert create.cr.status is SellerProfileChangeStatus.Approved
    assert create.cr.applied_json == create.cr.proposed_json
    logs = (
        await session.exec(
            select(AdminActionLog).where(AdminActionLog.action == "profile_cr_approve")
        )
    ).all()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_approve_with_edits_uses_admin_values(approved_seller, session, admin_user):
    from app.services.seller_profile_change_requests import (
        approve,
        create_change_request,
    )
    profile = approved_seller["profile"]
    create = await create_change_request(
        session=session, seller_profile=profile,
        group=SellerProfileChangeGroup.Banking,
        proposed={"bank_account_number": "123456789012", "bank_ifsc": "HDFC0000000"},
        note=None, actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    await approve(
        session=session, cr=create.cr,
        admin_user_id=admin_user.id,
        applied={"bank_account_number": "123456789012", "bank_ifsc": "HDFC0009999"},
        note="fixed IFSC for you",
    )
    await session.commit()
    await session.refresh(profile)
    assert profile.bank_ifsc == "HDFC0009999"
    assert create.cr.applied_json["bank_ifsc"] == "HDFC0009999"


@pytest.mark.asyncio
async def test_approve_invalid_applied_rejects(approved_seller, session, admin_user):
    from fastapi import HTTPException

    from app.services.seller_profile_change_requests import (
        approve,
        create_change_request,
    )
    profile = approved_seller["profile"]
    create = await create_change_request(
        session=session, seller_profile=profile,
        group=SellerProfileChangeGroup.Banking,
        proposed={"bank_account_number": "123456789012", "bank_ifsc": "HDFC0001234"},
        note=None, actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    with pytest.raises(HTTPException) as excinfo:
        await approve(
            session=session, cr=create.cr,
            admin_user_id=admin_user.id,
            applied={"bank_account_number": "123", "bank_ifsc": "ZZZZ"},
            note=None,
        )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_supersede_open_cr_marks_withdrawn_system(
    approved_seller, session, admin_user
):
    from app.models.seller_profile_change_request import (
        SellerProfileChangeEventKind,
    )
    from app.services.seller_profile_change_requests import (
        create_change_request,
        supersede_open_cr,
    )
    profile = approved_seller["profile"]
    create = await create_change_request(
        session=session, seller_profile=profile,
        group=SellerProfileChangeGroup.Services,
        proposed={"services": [{"service_id": 1, "min_order_value": 100.0}]},
        note=None, actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    await supersede_open_cr(
        session=session,
        seller_profile_id=profile.id,
        group=SellerProfileChangeGroup.Services,
        admin_user_id=admin_user.id,
        action_name="admin_set_services",
    )
    await session.commit()
    await session.refresh(create.cr)
    assert create.cr.status is SellerProfileChangeStatus.Withdrawn
    events = (
        await session.exec(
            select(SellerProfileChangeRequestEvent).where(
                SellerProfileChangeRequestEvent.change_request_id == create.cr.id
            )
        )
    ).all()
    kinds = [e.kind for e in events]
    assert SellerProfileChangeEventKind.Withdrawn in kinds


# ---------------------------------------------------------------------------
# API-level integration tests (Task 17)
# ---------------------------------------------------------------------------
@pytest.fixture
async def _approved_seller_auth(
    approved_seller: dict, admin_user: User
) -> AsyncIterator[dict]:
    """Override seller + admin auth deps with the in-DB users built by the
    conftest fixtures so route handlers see real DB rows.
    """
    seller_user: User = approved_seller["user"]
    app.dependency_overrides[get_current_seller] = lambda: seller_user
    app.dependency_overrides[get_current_admin] = lambda: admin_user
    app.dependency_overrides[get_current_user] = lambda: seller_user
    try:
        yield {
            "seller_user": seller_user,
            "admin_user": admin_user,
            "profile": approved_seller["profile"],
        }
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_api_seller_creates_and_admin_approves(
    _approved_seller_auth: dict,
    client: AsyncClient,
) -> None:
    seller_user: User = _approved_seller_auth["seller_user"]
    admin_user: User = _approved_seller_auth["admin_user"]
    profile_id: int = _approved_seller_auth["profile"].id
    # Admin URLs use User.id (matches every other /admin/sellers/{id}/* route).
    seller_user_id: int = seller_user.id

    # Seller creates a banking CR
    res = await client.post(
        "/api/v1/sellers/me/change-requests",
        json={
            "group": "banking",
            "proposed": {
                "bank_account_number": "123456789012",
                "bank_ifsc": "HDFC0001234",
            },
            "note": "please review",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    cr_id = body["id"]
    assert body["status"] == "submitted"
    assert body["seller_profile_id"] == profile_id

    # Admin approves the CR (swap dep override to admin for this call)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        res2 = await client.post(
            f"/api/v1/admin/sellers/{seller_user_id}/change-requests/{cr_id}/approve",
            json={},
        )
    finally:
        app.dependency_overrides[get_current_user] = lambda: seller_user
    assert res2.status_code == 200, res2.text
    body2 = res2.json()
    assert body2["status"] == "approved"
    assert body2["applied_json"]["bank_ifsc"] == "HDFC0001234"


# ---------------------------------------------------------------------------
# Legacy endpoint 409 guards (Task 18)
# ---------------------------------------------------------------------------
@pytest.fixture
async def _seller_auth_override(approved_seller: dict) -> AsyncIterator[dict]:
    seller_user: User = approved_seller["user"]
    app.dependency_overrides[get_current_seller] = lambda: seller_user
    app.dependency_overrides[get_current_user] = lambda: seller_user
    try:
        yield approved_seller
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def _approved_seller_store_id(approved_seller: dict) -> int:
    """Provision a Store row owned by the Approved seller built by the
    conftest fixture. Uses its own session so it does not collide with the
    test's session fixture (which is also wired to the test engine).
    """
    from sqlmodel.ext.asyncio.session import AsyncSession as _AsyncSession

    from app.models.address import Address as _Address
    from app.models.store import Store as _Store
    from tests.conftest import test_engine as _test_engine

    profile = approved_seller["profile"]
    async with _AsyncSession(_test_engine, expire_on_commit=False) as ses:
        store_addr = _Address(
            address_line1="Shop 1",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            country="India",
            latitude=19.07,
            longitude=72.87,
        )
        ses.add(store_addr)
        await ses.flush()
        store = _Store(
            name=profile.business_name,
            is_active=True,
            seller_profile_id=profile.id,
            address_id=store_addr.id,
            pin_confirmed=True,
        )
        ses.add(store)
        await ses.commit()
        await ses.refresh(store)
        return int(store.id)


@pytest.mark.asyncio
async def test_legacy_patch_profile_blocked_for_approved(
    _seller_auth_override: dict,
    client: AsyncClient,
) -> None:
    res = await client.patch(
        "/api/v1/sellers/me/profile",
        json={
            "full_name": "A B",
            "business_name": "X",
            "phone": "+919999999999",
            "address": {
                "address_line1": "1 Main",
                "city": "Mumbai",
                "state": "Maharashtra",
                "pincode": "400001",
                "country": "India",
                "latitude": 19.0,
                "longitude": 72.8,
            },
        },
    )
    assert res.status_code == 409, res.text
    assert res.json()["detail"] == "use_change_request"


@pytest.mark.asyncio
async def test_legacy_patch_store_blocked_for_approved(
    _seller_auth_override: dict,
    _approved_seller_store_id: int,
    client: AsyncClient,
) -> None:
    res = await client.patch(
        f"/api/v1/stores/{_approved_seller_store_id}",
        json={"delivery_radius_km": 8.0},
    )
    assert res.status_code == 409, res.text
    assert res.json()["detail"] == "use_change_request"


@pytest.mark.asyncio
async def test_legacy_patch_store_pin_confirm_still_allowed(
    _seller_auth_override: dict,
    _approved_seller_store_id: int,
    client: AsyncClient,
) -> None:
    res = await client.patch(
        f"/api/v1/stores/{_approved_seller_store_id}",
        json={"pin_confirmed": True},
    )
    assert res.status_code == 200, res.text
    assert res.json()["pin_confirmed"] is True


# ---------------------------------------------------------------------------
# Cross-seller queue: search + pagination (Task 4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_cr_queue_paginated_envelope(
    _approved_seller_auth: dict, session, client: AsyncClient
) -> None:
    from app.models.seller_profile_change_request import (
        SellerProfileChangeGroup,
        SellerProfileChangeRequest,
        SellerProfileChangeStatus,
    )

    profile_id: int = _approved_seller_auth["profile"].id
    for group in (SellerProfileChangeGroup.Banking, SellerProfileChangeGroup.Identity):
        session.add(
            SellerProfileChangeRequest(
                seller_profile_id=profile_id,
                group=group,
                status=SellerProfileChangeStatus.Submitted,
                proposed_json={},
                baseline_json={},
            )
        )
    await session.commit()

    resp = await client.get("/api/v1/admin/change-requests?status=open&page=1&page_size=1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["total"] == 2
    assert body["page"] == 1 and body["page_size"] == 1
    assert len(body["items"]) == 1


@pytest.mark.asyncio
async def test_admin_cr_queue_search_business_name(
    _approved_seller_auth: dict, session, client: AsyncClient
) -> None:
    from app.models.seller_profile_change_request import (
        SellerProfileChangeGroup,
        SellerProfileChangeRequest,
        SellerProfileChangeStatus,
    )

    profile = _approved_seller_auth["profile"]
    session.add(
        SellerProfileChangeRequest(
            seller_profile_id=profile.id,
            group=SellerProfileChangeGroup.Banking,
            status=SellerProfileChangeStatus.Submitted,
            proposed_json={},
            baseline_json={},
        )
    )
    await session.commit()

    term = profile.business_name[:3]
    hit = await client.get(f"/api/v1/admin/change-requests?status=all&q={term}")
    assert hit.status_code == 200
    hit_body = hit.json()
    assert hit_body["total"] == 1
    assert all(
        term.lower() in r["seller_business_name"].lower() for r in hit_body["items"]
    )

    miss = await client.get("/api/v1/admin/change-requests?status=all&q=zzzznomatch")
    assert miss.status_code == 200
    assert miss.json()["total"] == 0
    assert miss.json()["items"] == []
