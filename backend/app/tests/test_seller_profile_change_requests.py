# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from __future__ import annotations

import pytest
from sqlmodel import select

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
