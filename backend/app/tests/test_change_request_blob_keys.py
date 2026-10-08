# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""A seller never chooses a change request's storage key.

Withdrawing or rejecting an avatar / store-logo / payments-QR request deletes
its pending blob, so a key naming another user's blob would delete their
image. The generic routes refuse a key, a resubmission keeps the one filed
with the request, cleanup only deletes inside the seller's own folder, and the
local backend never leaves its media directory.
"""
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.profile import SellerProfile
from app.models.seller_profile_change_request import (
    SellerProfileChangeGroup,
    SellerProfileChangeRequest,
)
from app.models.store import Store
from app.services.image_storage import LocalImageStorage, key_in_scope
from app.services.seller_profile_change_requests import (
    create_change_request,
    reject,
    request_changes,
    withdraw,
)
from tests._courier_helpers import (
    ADMIN,
    SELLER,
    CourierWorld,
    client_as,
    seed_courier_world,
)

Group = SellerProfileChangeGroup


def _local_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))


def _blob(tmp_path: Path, key: str) -> Path:
    path = tmp_path / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"image")
    return path


async def _other_seller_keys(session: AsyncSession, world: CourierWorld) -> dict[Group, str]:
    """Blob keys inside the OTHER seller's folders — the victims."""
    other_store = (
        await session.exec(
            select(Store).where(Store.seller_profile_id == world.other_seller_profile_id)
        )
    ).one()
    return {
        Group.Avatar: f"avatars/seller/{world.other_seller_profile_id}/victim.webp",
        Group.StoreLogo: f"store-logos/{other_store.id}/victim.webp",
        Group.Payments: f"seller-upi-qr/{world.other_seller_profile_id}/victim.webp",
    }


def _own_key(world: CourierWorld, group: Group) -> str:
    return {
        Group.Avatar: f"avatars/seller/{world.seller_profile_id}/pending.webp",
        Group.StoreLogo: f"store-logos/{world.store_id}/pending.webp",
        Group.Payments: f"seller-upi-qr/{world.seller_profile_id}/pending.webp",
    }[group]


def _proposal(group: Group, key: str, *, url: str = "") -> dict[str, Any]:
    if group is Group.Avatar:
        return {"avatar_url": url, "storage_key": key}
    if group is Group.StoreLogo:
        return {"logo_url": url, "storage_key": key}
    return {"upi_vpa": "ravi.new@okicici", "upi_enabled": True, "upi_qr_url": url,
            "storage_key": key}


async def _file(
    session: AsyncSession, world: CourierWorld, group: Group, proposed: dict[str, Any]
) -> SellerProfileChangeRequest:
    """Straight through the service, as the old generic route allowed."""
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    res = await create_change_request(
        session=session, seller_profile=seller, group=group, proposed=proposed,
        note=None, actor_user_id=SELLER.id or 0,
    )
    await session.commit()
    return res.cr


IMAGE_GROUPS = [
    (Group.Avatar, "avatar_upload_required"),
    (Group.StoreLogo, "store_logo_upload_required"),
    (Group.Payments, "upi_qr_upload_required"),
]


@pytest.mark.parametrize(("group", "code"), IMAGE_GROUPS)
async def test_the_generic_route_refuses_a_storage_key(
    session: AsyncSession, group: Group, code: str
) -> None:
    world = await seed_courier_world(session)
    victim = (await _other_seller_keys(session, world))[group]
    async with client_as(SELLER) as ac:
        r = await ac.post(
            "/api/v1/sellers/me/change-requests",
            json={"group": group.value, "proposed": _proposal(group, victim)},
        )
    assert (r.status_code, r.json()["detail"]) == (422, code)


@pytest.mark.parametrize(("group", "code"), IMAGE_GROUPS)
async def test_a_resubmission_keeps_the_key_filed_with_the_request(
    session: AsyncSession, group: Group, code: str
) -> None:
    world = await seed_courier_world(session)
    own = _own_key(world, group)
    victim = (await _other_seller_keys(session, world))[group]
    cr = await _file(session, world, group, _proposal(group, own, url=f"/media/{own}"))
    await request_changes(
        session=session, cr=cr, admin_user_id=ADMIN.id or 0, note="Please try again"
    )
    await session.commit()
    forged = _proposal(group, victim)
    honest = {k: v for k, v in forged.items() if k != "storage_key"}
    async with client_as(SELLER) as ac:
        refused = await ac.patch(
            f"/api/v1/sellers/me/change-requests/{cr.id}/resubmit", json={"proposed": forged}
        )
        kept = await ac.patch(
            f"/api/v1/sellers/me/change-requests/{cr.id}/resubmit", json={"proposed": honest}
        )
    assert (refused.status_code, refused.json()["detail"]) == (422, code)
    assert kept.status_code == 200, kept.text
    assert kept.json()["proposed_json"]["storage_key"] == own


@pytest.mark.parametrize("group", [g for g, _ in IMAGE_GROUPS])
async def test_withdrawing_never_deletes_another_sellers_blob(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, group: Group
) -> None:
    """A key planted before the fix (the service takes any key) is left alone,
    while the seller's own pending blob is still cleaned up."""
    _local_storage(monkeypatch, tmp_path)
    world = await seed_courier_world(session)
    victim_key = (await _other_seller_keys(session, world))[group]
    victim = _blob(tmp_path, victim_key)
    planted = await _file(session, world, group, _proposal(group, victim_key))
    await withdraw(session=session, cr=planted, actor_user_id=SELLER.id or 0)
    await session.commit()
    assert victim.exists()

    own_key = _own_key(world, group)
    own = _blob(tmp_path, own_key)
    mine = await _file(session, world, group, _proposal(group, own_key, url=f"/media/{own_key}"))
    await withdraw(session=session, cr=mine, actor_user_id=SELLER.id or 0)
    await session.commit()
    assert not own.exists()


async def test_rejecting_never_deletes_another_sellers_blob(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _local_storage(monkeypatch, tmp_path)
    world = await seed_courier_world(session)
    victim_key = (await _other_seller_keys(session, world))[Group.Payments]
    victim = _blob(tmp_path, victim_key)
    planted = await _file(session, world, Group.Payments, _proposal(Group.Payments, victim_key))
    await reject(
        session=session, cr=planted, admin_user_id=ADMIN.id or 0, reason="Not your image"
    )
    await session.commit()
    assert victim.exists()


def test_a_key_is_in_scope_only_inside_its_folder() -> None:
    assert key_in_scope("avatars/seller/7/a.webp", "avatars/seller/7/")
    assert not key_in_scope("avatars/seller/70/a.webp", "avatars/seller/7/")
    assert not key_in_scope("avatars/seller/7/../8/a.webp", "avatars/seller/7/")
    assert not key_in_scope("avatars/seller/8/a.webp", "avatars/seller/7/")


async def test_local_storage_stays_inside_its_media_directory(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    storage = LocalImageStorage(str(media), "/media")
    for key in ("../outside.txt", "avatars/../../outside.txt", str(outside), ""):
        with pytest.raises(ValueError):
            await storage.delete(key)
        with pytest.raises(ValueError):
            await storage.save(key, b"x", "image/webp")
    assert outside.read_text() == "keep"

    url = await storage.save("avatars/seller/1/a.webp", b"x", "image/webp")
    assert url == "/media/avatars/seller/1/a.webp"
    assert (media / "avatars/seller/1/a.webp").exists()
    await storage.delete("avatars/seller/1/a.webp")
    assert not (media / "avatars/seller/1/a.webp").exists()
