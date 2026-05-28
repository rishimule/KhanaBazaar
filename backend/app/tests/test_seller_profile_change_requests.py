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
        create_change_request, withdraw,
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
        create_change_request, resubmit,
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
        create_change_request, request_changes, resubmit,
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
    from app.services.seller_profile_change_requests import (
        create_change_request, request_changes,
    )
    from app.models.admin_audit import AdminActionLog
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
        create_change_request, reject, resubmit,
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
