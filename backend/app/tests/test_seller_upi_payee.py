# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
"""Seller UPI payee: model columns, CR group, payload validation, QR storage
helper, and the change-request apply flow.

Mirrors the store-logo suite (test_store_logo.py). Uses the local
image-storage backend against tmp_path so no GCS/network is touched."""
import io
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.config import settings
from app.core.security import get_current_admin, get_current_seller
from app.models.commerce import Payment
from app.models.profile import SellerProfile
from app.models.seller_profile_change_request import (
    SellerProfileChangeGroup,
    SellerProfileChangeStatus,
)
from app.schemas.seller_profile_change_request import validate_group_payload
from app.services import seller_upi_qr
from app.services.seller_profile_change_requests import (
    approve,
    create_change_request,
    create_payments_qr_change_request,
)


def test_seller_profile_has_upi_columns() -> None:
    assert {
        "upi_vpa",
        "upi_qr_url",
        "upi_qr_storage_key",
        "upi_enabled",
    } <= set(SellerProfile.model_fields.keys())


def test_upi_enabled_defaults_false() -> None:
    assert SellerProfile.model_fields["upi_enabled"].default is False


def test_payment_has_customer_claimed_at() -> None:
    assert "customer_claimed_at" in Payment.model_fields


def test_payments_group_value() -> None:
    assert SellerProfileChangeGroup.Payments.value == "payments"


# ── C2: VPA payload validation ────────────────────────────────────────
@pytest.mark.parametrize(
    "vpa",
    ["name@okhdfcbank", "9876543210@paytm", "a.b-c_d@ybl", "x2@sbi"],
)
def test_valid_vpas_accepted(vpa: str) -> None:
    out = validate_group_payload(
        SellerProfileChangeGroup.Payments, {"upi_vpa": vpa, "upi_enabled": True}
    )
    assert out["upi_vpa"] == vpa
    assert out["upi_enabled"] is True


@pytest.mark.parametrize(
    "vpa",
    [
        "nobank",            # no @
        "@okhdfcbank",       # empty handle
        "name@",             # empty bank
        "name@1bank",        # bank must start with a letter
        "a@ybl",             # handle shorter than 2 chars
        "name@@ybl",         # double @
        "na me@ybl",         # whitespace
    ],
)
def test_invalid_vpas_rejected(vpa: str) -> None:
    with pytest.raises(ValidationError):
        validate_group_payload(
            SellerProfileChangeGroup.Payments, {"upi_vpa": vpa}
        )


def test_enabled_without_vpa_rejected() -> None:
    """The core invariant: UPI cannot be on with no payee to pay."""
    with pytest.raises(ValidationError):
        validate_group_payload(
            SellerProfileChangeGroup.Payments,
            {"upi_vpa": None, "upi_enabled": True},
        )


def test_payments_removal_payload() -> None:
    out = validate_group_payload(
        SellerProfileChangeGroup.Payments, {"upi_vpa": "", "upi_enabled": False}
    )
    assert out["upi_vpa"] is None
    assert out["upi_enabled"] is False
    assert out["upi_qr_url"] == ""
    assert out["storage_key"] is None


# ── C3: QR verification-blob storage helper ───────────────────────────
def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), "black").save(buf, format="PNG")
    return buf.getvalue()


def _local_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))


@pytest.mark.asyncio
async def test_upi_qr_process_and_store_returns_prefixed_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    _local_storage(monkeypatch, tmp_path)
    url, key = await seller_upi_qr.process_and_store(_png(), seller_profile_id=7)
    assert key.startswith("seller-upi-qr/7/")
    assert key.endswith(".webp")
    assert url
    assert (tmp_path / key).exists()


@pytest.mark.asyncio
async def test_upi_qr_delete_blob_tolerates_none() -> None:
    """Never raises: a storage error must not abort the caller's transaction."""
    await seller_upi_qr.delete_blob(None)


# ── C4: change-request baseline / apply / removal ─────────────────────
@pytest.mark.asyncio
async def test_payments_cr_approve_sets_profile(
    approved_seller_with_store: Any,
    session: AsyncSession,
    admin_user: Any,
) -> None:
    bundle = approved_seller_with_store
    res = await create_change_request(
        session=session,
        seller_profile=bundle.profile,
        group=SellerProfileChangeGroup.Payments,
        proposed={"upi_vpa": "ganesh@okhdfcbank", "upi_enabled": True},
        note=None,
        actor_user_id=bundle.user.id,
    )
    await session.commit()
    assert res.cr.status is SellerProfileChangeStatus.Submitted

    await approve(session=session, cr=res.cr, admin_user_id=admin_user.id)
    await session.commit()
    await session.refresh(bundle.profile)
    assert bundle.profile.upi_vpa == "ganesh@okhdfcbank"
    assert bundle.profile.upi_enabled is True


@pytest.mark.asyncio
async def test_payments_cr_keeps_old_payee_live_until_approval(
    approved_seller_with_store: Any,
    session: AsyncSession,
) -> None:
    """A pending VPA change must not disturb the live payee."""
    bundle = approved_seller_with_store
    bundle.profile.upi_vpa = "old@okaxis"
    bundle.profile.upi_enabled = True
    session.add(bundle.profile)
    await session.commit()

    await create_change_request(
        session=session,
        seller_profile=bundle.profile,
        group=SellerProfileChangeGroup.Payments,
        proposed={"upi_vpa": "new@okhdfcbank", "upi_enabled": True},
        note=None,
        actor_user_id=bundle.user.id,
    )
    await session.commit()
    await session.refresh(bundle.profile)
    assert bundle.profile.upi_vpa == "old@okaxis"


@pytest.mark.asyncio
async def test_payments_cr_baseline_snapshots_current_payee(
    approved_seller_with_store: Any,
    session: AsyncSession,
) -> None:
    bundle = approved_seller_with_store
    bundle.profile.upi_vpa = "old@okaxis"
    bundle.profile.upi_enabled = True
    session.add(bundle.profile)
    await session.commit()

    res = await create_change_request(
        session=session,
        seller_profile=bundle.profile,
        group=SellerProfileChangeGroup.Payments,
        proposed={"upi_vpa": "new@okhdfcbank", "upi_enabled": True},
        note=None,
        actor_user_id=bundle.user.id,
    )
    await session.commit()
    assert res.cr.baseline_json["upi_vpa"] == "old@okaxis"
    assert res.cr.baseline_json["upi_enabled"] is True


@pytest.mark.asyncio
async def test_payments_cr_removal_clears_payee(
    approved_seller_with_store: Any,
    session: AsyncSession,
    admin_user: Any,
) -> None:
    bundle = approved_seller_with_store
    bundle.profile.upi_vpa = "old@okaxis"
    bundle.profile.upi_enabled = True
    session.add(bundle.profile)
    await session.commit()

    res = await create_change_request(
        session=session,
        seller_profile=bundle.profile,
        group=SellerProfileChangeGroup.Payments,
        proposed={"upi_vpa": "", "upi_enabled": False},
        note=None,
        actor_user_id=bundle.user.id,
    )
    await session.commit()
    await approve(session=session, cr=res.cr, admin_user_id=admin_user.id)
    await session.commit()
    await session.refresh(bundle.profile)
    assert bundle.profile.upi_vpa is None
    assert bundle.profile.upi_enabled is False


# ── C5: QR upload route + forged-image guard ──────────────────────────
@pytest.mark.asyncio
async def test_payments_qr_upload_creates_cr_with_vpa_and_key(
    approved_seller_with_store: Any,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    _local_storage(monkeypatch, tmp_path)
    bundle = approved_seller_with_store
    res = await create_payments_qr_change_request(
        session=session,
        seller_profile=bundle.profile,
        raw=_png(),
        upi_vpa="ganesh@okhdfcbank",
        actor_user_id=bundle.user.id,
    )
    await session.commit()
    assert res.cr.group is SellerProfileChangeGroup.Payments
    assert res.cr.proposed_json["upi_vpa"] == "ganesh@okhdfcbank"
    assert res.cr.proposed_json["storage_key"].startswith("seller-upi-qr/")
    assert res.cr.proposed_json["upi_enabled"] is True


@pytest.mark.asyncio
async def test_payments_qr_second_upload_supersedes_first(
    approved_seller_with_store: Any,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    _local_storage(monkeypatch, tmp_path)
    bundle = approved_seller_with_store
    first = await create_payments_qr_change_request(
        session=session, seller_profile=bundle.profile, raw=_png(),
        upi_vpa="ab@okaxis", actor_user_id=bundle.user.id,
    )
    await session.commit()
    second = await create_payments_qr_change_request(
        session=session, seller_profile=bundle.profile, raw=_png(),
        upi_vpa="bc@okhdfcbank", actor_user_id=bundle.user.id,
    )
    await session.commit()
    await session.refresh(first.cr)
    assert first.cr.status is SellerProfileChangeStatus.Withdrawn
    assert second.cr.status is SellerProfileChangeStatus.Submitted


def test_generic_cr_path_rejects_forged_upi_qr_url() -> None:
    """A seller must not be able to point upi_qr_url at an arbitrary blob."""
    from fastapi import HTTPException

    from app.api.seller_change_requests import _reject_forged_image

    with pytest.raises(HTTPException) as exc:
        _reject_forged_image(
            SellerProfileChangeGroup.Payments,
            {"upi_vpa": "ab@okaxis", "upi_qr_url": "https://evil/x.webp"},
        )
    assert exc.value.detail == "upi_qr_upload_required"


def test_generic_cr_path_allows_vpa_only_edit() -> None:
    """VPA-only edits (no image) must still flow through the generic path."""
    from app.api.seller_change_requests import _reject_forged_image

    _reject_forged_image(
        SellerProfileChangeGroup.Payments,
        {"upi_vpa": "ab@okaxis", "upi_qr_url": ""},
    )


# ── C6: immediate disable (deliberately not moderated) ────────────────
@pytest.mark.asyncio
async def test_disable_upi_is_immediate_and_keeps_vpa(
    approved_seller_with_store: Any,
    session: AsyncSession,
) -> None:
    bundle = approved_seller_with_store
    bundle.profile.upi_vpa = "ganesh@okhdfcbank"
    bundle.profile.upi_enabled = True
    session.add(bundle.profile)
    await session.commit()

    app.dependency_overrides[get_current_seller] = lambda: bundle.user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.patch("/api/v1/sellers/me/payments/disable")
        assert r.status_code == 200
        assert r.json()["upi_enabled"] is False
    finally:
        app.dependency_overrides.pop(get_current_seller, None)

    await session.refresh(bundle.profile)
    assert bundle.profile.upi_enabled is False
    # VPA survives so re-enabling needs no fresh review.
    assert bundle.profile.upi_vpa == "ganesh@okhdfcbank"


@pytest.mark.asyncio
async def test_disable_upi_is_idempotent(
    approved_seller_with_store: Any,
    session: AsyncSession,
) -> None:
    bundle = approved_seller_with_store
    app.dependency_overrides[get_current_seller] = lambda: bundle.user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            first = await ac.patch("/api/v1/sellers/me/payments/disable")
            second = await ac.patch("/api/v1/sellers/me/payments/disable")
        assert first.status_code == 200
        assert second.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_seller, None)


# ── C7: registration capture + enable-on-approval ─────────────────────
def test_register_body_accepts_optional_upi_vpa() -> None:
    """Optional at registration: a seller without their UPI ID to hand must
    still be able to finish signup (design spec §4.1)."""
    from app.schemas.sellers import SellerRegisterBody

    assert "upi_vpa" in SellerRegisterBody.model_fields
    assert SellerRegisterBody.model_fields["upi_vpa"].is_required() is False


def test_register_body_rejects_malformed_upi_vpa() -> None:
    from app.schemas.sellers import SellerRegisterBody
    from tests._helpers import make_address

    with pytest.raises(ValidationError):
        SellerRegisterBody.model_validate(
            {
                "signup_token": "t",
                "full_name": "A B",
                "business_name": "Shop",
                "service_ids": [1],
                "address": make_address(),
                "upi_vpa": "nobank",
            }
        )


@pytest.mark.asyncio
async def test_approval_enables_upi_when_vpa_present(
    approved_seller_with_store: Any,
    session: AsyncSession,
    admin_user: Any,
) -> None:
    """Approving a seller who supplied a VPA at signup turns UPI on, so there
    is no second gate after onboarding."""
    from app.models.profile import VerificationStatus

    bundle = approved_seller_with_store
    # Rewind to pending with a VPA on file, then approve through the route.
    bundle.profile.verification_status = VerificationStatus.Pending
    bundle.profile.upi_vpa = "ganesh@okhdfcbank"
    bundle.profile.upi_enabled = False
    session.add(bundle.profile)
    await session.commit()

    app.dependency_overrides[get_current_admin] = lambda: admin_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.patch(
                f"/api/v1/sellers/admin/{bundle.profile.id}/verify",
                json={"action": "approve"},
            )
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.pop(get_current_admin, None)

    await session.refresh(bundle.profile)
    assert bundle.profile.upi_enabled is True


@pytest.mark.asyncio
async def test_approval_leaves_upi_off_without_vpa(
    approved_seller_with_store: Any,
    session: AsyncSession,
    admin_user: Any,
) -> None:
    """No payee means UPI stays off — the invariant holds at approval too."""
    from app.models.profile import VerificationStatus

    bundle = approved_seller_with_store
    bundle.profile.verification_status = VerificationStatus.Pending
    bundle.profile.upi_vpa = None
    bundle.profile.upi_enabled = False
    session.add(bundle.profile)
    await session.commit()

    app.dependency_overrides[get_current_admin] = lambda: admin_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.patch(
                f"/api/v1/sellers/admin/{bundle.profile.id}/verify",
                json={"action": "approve"},
            )
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.pop(get_current_admin, None)

    await session.refresh(bundle.profile)
    assert bundle.profile.upi_enabled is False
