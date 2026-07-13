# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
"""Store-logo feature: model columns, storage helper, change-request flow
(seller CR + admin direct-apply), and StoreRead serialization.

Mirrors the seller-avatar test suite (test_seller_avatar_*). Uses the local
image-storage backend against tmp_path so no GCS/network is touched."""
import io
from typing import Any, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.config import settings
from app.core.security import (
    get_current_admin,
    get_current_seller,
    get_current_user,
)
from app.models.admin_audit import AdminActionLog
from app.models.profile import VerificationStatus
from app.models.seller_profile_change_request import (
    SellerProfileChangeGroup,
    SellerProfileChangeStatus,
)
from app.models.store import Store
from app.schemas.seller_profile_change_request import validate_group_payload
from app.services import store_logos
from app.services.seller_profile_change_requests import (
    approve,
    create_change_request,
    create_store_logo_change_request,
    reject,
)


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), "green").save(buf, format="PNG")
    return buf.getvalue()


def _local_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))


# ── C1: model + enum ──────────────────────────────────────────────────
def test_store_has_logo_columns() -> None:
    assert {"logo_url", "logo_storage_key"} <= set(Store.model_fields.keys())


def test_store_logo_group_value() -> None:
    assert SellerProfileChangeGroup.StoreLogo.value == "store_logo"


# ── C2: storage helper ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_process_and_store_returns_prefixed_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    _local_storage(monkeypatch, tmp_path)
    url, key = await store_logos.process_and_store(_png(), store_id=42)
    assert key.startswith("store-logos/42/")
    assert key.endswith(".webp")
    assert url
    assert (tmp_path / key).exists()


# ── C3: payload validation ────────────────────────────────────────────
def test_validate_store_logo_payload_roundtrip() -> None:
    out = validate_group_payload(
        SellerProfileChangeGroup.StoreLogo,
        {"logo_url": "https://x/y.webp", "storage_key": "store-logos/1/a.webp"},
    )
    assert out == {
        "logo_url": "https://x/y.webp",
        "storage_key": "store-logos/1/a.webp",
    }


def test_validate_store_logo_removal_payload() -> None:
    out = validate_group_payload(
        SellerProfileChangeGroup.StoreLogo, {"logo_url": ""}
    )
    assert out["logo_url"] == ""
    assert out["storage_key"] is None


# ── C4: CR create / approve / removal / reject ────────────────────────
@pytest.mark.asyncio
async def test_store_logo_cr_create_then_approve_sets_store(
    approved_seller_with_store: Any,
    session: AsyncSession,
    admin_user: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    _local_storage(monkeypatch, tmp_path)
    bundle = approved_seller_with_store
    res = await create_store_logo_change_request(
        session=session,
        seller_profile=bundle.profile,
        raw=_png(),
        actor_user_id=bundle.user.id,
    )
    await session.commit()
    assert res.cr.group is SellerProfileChangeGroup.StoreLogo
    assert res.cr.status is SellerProfileChangeStatus.Submitted

    await approve(session=session, cr=res.cr, admin_user_id=admin_user.id)
    await session.commit()
    store = (
        await session.exec(
            select(Store).where(Store.seller_profile_id == bundle.profile.id)
        )
    ).first()
    assert store is not None
    assert store.logo_url
    assert store.logo_storage_key is not None
    assert store.logo_storage_key.startswith("store-logos/")


@pytest.mark.asyncio
async def test_store_logo_removal_clears_store(
    approved_seller_with_store: Any,
    session: AsyncSession,
    admin_user: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    _local_storage(monkeypatch, tmp_path)
    bundle = approved_seller_with_store
    bundle.store.logo_url = "https://x/y.webp"
    bundle.store.logo_storage_key = "store-logos/1/old.webp"
    session.add(bundle.store)
    await session.commit()

    res = await create_change_request(
        session=session,
        seller_profile=bundle.profile,
        group=SellerProfileChangeGroup.StoreLogo,
        proposed={"logo_url": ""},
        note=None,
        actor_user_id=bundle.user.id,
    )
    await session.commit()
    await approve(session=session, cr=res.cr, admin_user_id=admin_user.id)
    await session.commit()
    await session.refresh(bundle.store)
    assert bundle.store.logo_url is None
    assert bundle.store.logo_storage_key is None


@pytest.mark.asyncio
async def test_store_logo_reject_deletes_pending_blob(
    approved_seller_with_store: Any,
    session: AsyncSession,
    admin_user: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    _local_storage(monkeypatch, tmp_path)
    bundle = approved_seller_with_store
    res = await create_store_logo_change_request(
        session=session,
        seller_profile=bundle.profile,
        raw=_png(),
        actor_user_id=bundle.user.id,
    )
    await session.commit()
    key = res.cr.proposed_json["storage_key"]
    assert (tmp_path / key).exists()
    await reject(
        session=session, cr=res.cr, admin_user_id=admin_user.id,
        reason="logo not acceptable",
    )
    await session.commit()
    assert not (tmp_path / key).exists()


# ── C5: seller upload route + generic-path forgery guard ──────────────
@pytest.fixture
def _as_seller(approved_seller_with_store: Any) -> Iterator[Any]:
    user = approved_seller_with_store.user
    app.dependency_overrides[get_current_seller] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user
    yield approved_seller_with_store
    app.dependency_overrides.pop(get_current_seller, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_seller_upload_store_logo_creates_cr(
    _as_seller: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    _local_storage(monkeypatch, tmp_path)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            "/api/v1/sellers/me/store/logo",
            files={"file": ("logo.png", _png(), "image/png")},
        )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["group"] == "store_logo"
    assert body["status"] == "submitted"
    assert body["proposed_json"]["logo_url"]


@pytest.mark.asyncio
async def test_generic_cr_rejects_forged_store_logo(_as_seller: Any) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            "/api/v1/sellers/me/change-requests",
            json={
                "group": "store_logo",
                "proposed": {"logo_url": "https://evil.example/x.webp"},
            },
        )
    assert res.status_code == 422
    assert res.json()["detail"] == "store_logo_upload_required"


@pytest.mark.asyncio
async def test_generic_cr_allows_store_logo_removal(_as_seller: Any) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            "/api/v1/sellers/me/change-requests",
            json={"group": "store_logo", "proposed": {"logo_url": ""}},
        )
    assert res.status_code == 201, res.text
    assert res.json()["group"] == "store_logo"


# ── C6: admin direct-apply route ──────────────────────────────────────
@pytest.fixture
def _as_admin(admin_user: Any) -> Iterator[Any]:
    app.dependency_overrides[get_current_admin] = lambda: admin_user
    app.dependency_overrides[get_current_user] = lambda: admin_user
    yield admin_user
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_upload_store_logo_applies_immediately(
    _as_admin: Any,
    approved_seller_with_store: Any,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    _local_storage(monkeypatch, tmp_path)
    seller_user_id = approved_seller_with_store.user.id
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            f"/api/v1/admin/sellers/{seller_user_id}/store/logo",
            files={"file": ("logo.png", _png(), "image/png")},
        )
    assert res.status_code == 200, res.text
    assert res.json()["logo_url"]
    rows = (
        await session.exec(
            select(AdminActionLog).where(
                AdminActionLog.action == "store.set_logo"
            )
        )
    ).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_admin_upload_store_logo_rejects_non_approved(
    _as_admin: Any,
    approved_seller_with_store: Any,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    _local_storage(monkeypatch, tmp_path)
    bundle = approved_seller_with_store
    bundle.profile.verification_status = VerificationStatus.Pending
    session.add(bundle.profile)
    await session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            f"/api/v1/admin/sellers/{bundle.user.id}/store/logo",
            files={"file": ("logo.png", _png(), "image/png")},
        )
    assert res.status_code == 409
    assert res.json()["detail"] == "seller_not_active"


# ── C7: StoreRead serialization ───────────────────────────────────────
@pytest.mark.asyncio
async def test_store_detail_includes_logo_url(
    client: AsyncClient,
    approved_seller_with_store: Any,
    session: AsyncSession,
) -> None:
    bundle = approved_seller_with_store
    bundle.store.logo_url = "https://x/y.webp"
    session.add(bundle.store)
    await session.commit()
    res = await client.get(f"/api/v1/stores/{bundle.store.id}")
    assert res.status_code == 200, res.text
    assert res.json()["logo_url"] == "https://x/y.webp"
