# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Which zone a location falls in for a store: local, courier, or none.

The single home of the delivery-radius rule (spec 2026-10-02 §5). Availability
— store paused, service paused, fee suspended — is deliberately NOT part of a
zone: checkout and the listings already enforce those with their own messages,
so a paused store keeps showing its pause banner instead of "out of range".

Listing queries build on the SQL fragments below (`LOCAL_SQL`,
`zone_case_sql`); per-point lookups use `zone_for_point` and
`compute_locality`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import bindparam, text
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.commerce import DeliveryMode, PaymentMethod
from app.models.profile import SellerProfile, SellerProfileService
from app.models.store import Store

# Re-exported: courier, checkout and tests import it from here.
from app.services.payment_methods import bank_transfer_live as bank_transfer_live
from app.services.payment_methods import methods_for

Zone = Literal["local", "courier", "none"]
Fulfilment = Literal["local", "courier"]

_INDIA_PIN_RE = re.compile(r"^[1-9]\d{5}$")
_INDIA_BBOX = (6.5, 36.0, 68.0, 98.0)  # lat_min, lat_max, lng_min, lng_max


def in_india_bbox(lat: float, lng: float) -> bool:
    """A rough filter for raw map points. It also covers Nepal, Bangladesh and
    Bhutan, which is why checkout checks the saved address's country instead."""
    return (
        _INDIA_BBOX[0] <= lat <= _INDIA_BBOX[1]
        and _INDIA_BBOX[2] <= lng <= _INDIA_BBOX[3]
    )


@dataclass(frozen=True)
class StoreZone:
    zone: Zone
    distance_km: float | None = None
    # Services that can ship by courier to this point; empty unless "courier".
    courier_service_ids: tuple[int, ...] = ()


def courier_payment_methods(seller: SellerProfile) -> list[PaymentMethod]:
    """Prepaid methods a courier customer can pay this seller by, UPI first.
    The rules live in services/payment_methods.py."""
    return methods_for(seller, DeliveryMode.Courier)


def is_courier_destination(address: Address) -> bool:
    """A saved address a courier can deliver to: in India with a 6-digit PIN.

    The India bounding box is not enough here — it also covers Nepal,
    Bangladesh and Bhutan — so checkout uses the address's own country.
    """
    return address.country == "India" and bool(_INDIA_PIN_RE.match(address.pincode or ""))


async def courier_service_ids(session: AsyncSession, store_id: int) -> tuple[int, ...]:
    """Services at `store_id` that can take a courier order, ignoring location:
    a courier radius is set, the service has courier on, and the seller has at
    least one live prepaid payee."""
    row = (
        await session.exec(
            select(Store, SellerProfile)
            .join(SellerProfile, SellerProfile.id == Store.seller_profile_id)  # type: ignore[arg-type]
            .where(Store.id == store_id)
        )
    ).first()
    if row is None:
        return ()
    store, seller = row
    if store.courier_radius_km is None or not courier_payment_methods(seller):
        return ()
    ids = (
        await session.exec(
            select(SellerProfileService.service_id)
            .where(
                SellerProfileService.seller_profile_id == seller.id,
                SellerProfileService.courier_enabled == True,  # noqa: E712
            )
            .order_by(col(SellerProfileService.service_id))
        )
    ).all()
    return tuple(int(i) for i in ids)


# ── SQL fragments for listing queries ────────────────────────────────────────
# Aliases: s = store, a = the store's address (its `geo` column), sp = the
# store's seller profile. Bind :lat and :lng, plus :in_india for the courier
# parts (zone_params builds all three). `service_expr` arguments are SQL that
# callers in this codebase write (a bind name or a column) — never user input.

POINT_SQL = "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography"
LOCAL_SQL = f"ST_DWithin(a.geo, {POINT_SQL}, s.delivery_radius_km * 1000)"
# The courier ring starts strictly beyond the local radius (spec §5.3).
_COURIER_RING_SQL = (
    f"(s.courier_radius_km IS NOT NULL AND NOT {LOCAL_SQL} "
    f"AND ST_DWithin(a.geo, {POINT_SQL}, s.courier_radius_km * 1000))"
)
# SQL twin of courier_payment_methods() (payment_methods.upi_live /
# bank_transfer_live): UPI, or bank transfer fully specified.
_PAYEE_LIVE_SQL = (
    "((sp.upi_enabled AND COALESCE(sp.upi_vpa, '') <> '') "
    "OR (sp.bank_transfer_enabled AND COALESCE(sp.bank_account_name, '') <> '' "
    "AND COALESCE(sp.bank_account_number, '') <> '' "
    "AND COALESCE(sp.bank_ifsc, '') <> ''))"
)


def courier_zone_sql(service_expr: str | None = None) -> str:
    """True where the point is in the courier ring, inside India, the seller has
    a live payee, and the service — or, with no `service_expr`, any of the
    store's services — ships by courier."""
    service = f" AND sps.service_id = {service_expr}" if service_expr else ""
    return (
        f"(CAST(:in_india AS boolean) AND {_COURIER_RING_SQL} AND {_PAYEE_LIVE_SQL} "
        "AND EXISTS (SELECT 1 FROM sellerprofile_service sps "
        "WHERE sps.seller_profile_id = s.seller_profile_id AND sps.courier_enabled"
        f"{service}))"
    )


def zone_case_sql(service_expr: str | None = None) -> str:
    """'local', 'courier' or NULL for each store row (see courier_zone_sql)."""
    return (
        f"CASE WHEN {LOCAL_SQL} THEN 'local' "
        f"WHEN {courier_zone_sql(service_expr)} THEN 'courier' END"
    )


def zone_params(lat: float, lng: float) -> dict[str, float | bool]:
    return {"lat": lat, "lng": lng, "in_india": in_india_bbox(lat, lng)}


_ZONE_SQL = text(
    f"SELECT ST_Distance(a.geo, {POINT_SQL}) / 1000.0 AS distance_km, "
    f"  {LOCAL_SQL} AS in_local, "
    f"  COALESCE(ST_DWithin(a.geo, {POINT_SQL}, s.courier_radius_km * 1000), false) AS in_courier "
    "FROM store s JOIN address a ON a.id = s.address_id "
    "WHERE s.id = :store_id AND s.is_active AND a.geo IS NOT NULL"
)


async def zone_for_point(
    session: AsyncSession,
    *,
    store_id: int,
    lat: float,
    lng: float,
    service_id: int | None = None,
) -> StoreZone:
    """Zone of (lat, lng) for a store. With `service_id`, courier counts only
    when that service can ship; without it, when any of its services can."""
    result = await session.exec(  # type: ignore[call-overload]
        _ZONE_SQL.bindparams(store_id=store_id, lat=lat, lng=lng)
    )
    row = result.first()
    if row is None:
        return StoreZone(zone="none")
    distance_km = float(row.distance_km)
    if row.in_local:
        return StoreZone(zone="local", distance_km=distance_km)
    if not row.in_courier or not in_india_bbox(lat, lng):
        return StoreZone(zone="none", distance_km=distance_km)
    capable = await courier_service_ids(session, store_id)
    if service_id is not None:
        capable = tuple(s for s in capable if s == service_id)
    if not capable:
        return StoreZone(zone="none", distance_km=distance_km)
    return StoreZone(zone="courier", distance_km=distance_km, courier_service_ids=capable)


async def zone_for_address(
    session: AsyncSession,
    *,
    store_id: int,
    address_id: int,
    service_id: int | None = None,
) -> StoreZone:
    """Zone for an `Address` row (by Address.id). No coordinates → none."""
    address = await session.get(Address, address_id)
    if address is None or address.latitude is None or address.longitude is None:
        return StoreZone(zone="none")
    return await zone_for_point(
        session,
        store_id=store_id,
        lat=address.latitude,
        lng=address.longitude,
        service_id=service_id,
    )


_WITHIN_LOCAL_SQL = text(
    f"SELECT {LOCAL_SQL} FROM store s JOIN address a ON a.id = s.address_id "
    "WHERE s.id = :store_id AND a.geo IS NOT NULL"
)


async def within_local_radius(
    session: AsyncSession, *, store_id: int, lat: float, lng: float
) -> bool:
    """The local-delivery test alone, whatever the store's status. Door
    checkout reports an inactive store as `store_unavailable` in a later
    check; the admin address override never looked at store status. Both
    keep that behaviour."""
    result = await session.exec(  # type: ignore[call-overload]
        _WITHIN_LOCAL_SQL.bindparams(store_id=store_id, lat=lat, lng=lng)
    )
    return bool(result.scalar_one_or_none())


@dataclass(frozen=True)
class Locality:
    """The stores that serve a point. `local` deliver to the door; `courier`
    maps a service id to the stores that ship it there. The two never
    overlap: a store local to the point is never listed under courier."""

    local: tuple[int, ...] = ()
    courier: dict[int, tuple[int, ...]] = field(default_factory=dict)

    # Holds a dict, so it can't be hashed; say so instead of failing in hash().
    __hash__ = None  # type: ignore[assignment]

    @property
    def courier_store_ids(self) -> frozenset[int]:
        return frozenset(s for ids in self.courier.values() for s in ids)

    @property
    def is_empty(self) -> bool:
        return not self.local and not self.courier

    def fulfilment(self, store_id: int, service_id: int | None = None) -> Fulfilment | None:
        """How `store_id` reaches the point — for `service_id` when given."""
        if store_id in self.local:
            return "local"
        if service_id is None:
            return "courier" if store_id in self.courier_store_ids else None
        return "courier" if store_id in self.courier.get(service_id, ()) else None

    def to_json(self) -> str:
        return json.dumps(
            {
                "local": list(self.local),
                "courier": {str(k): list(v) for k, v in self.courier.items()},
            }
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> Locality:
        data = json.loads(raw)
        return cls(
            local=tuple(int(i) for i in data["local"]),
            courier={int(k): tuple(int(i) for i in v) for k, v in data["courier"].items()},
        )


_LOCAL_STORES_SQL = text(
    "SELECT s.id FROM store s JOIN address a ON a.id = s.address_id "
    f"WHERE s.is_active AND a.geo IS NOT NULL AND {LOCAL_SQL} ORDER BY s.id"
)
_COURIER_PAIRS_SQL = text(
    "SELECT s.id, sps.service_id FROM store s "
    "JOIN address a ON a.id = s.address_id "
    "JOIN sellerprofile sp ON sp.id = s.seller_profile_id "
    "JOIN sellerprofile_service sps ON sps.seller_profile_id = s.seller_profile_id "
    "  AND sps.courier_enabled "
    f"WHERE s.is_active AND a.geo IS NOT NULL AND {_COURIER_RING_SQL} "
    f"  AND {_PAYEE_LIVE_SQL} "
    "ORDER BY sps.service_id, s.id"
)


async def compute_locality(session: AsyncSession, *, lat: float, lng: float) -> Locality:
    """Every store serving (lat, lng): the local ones, and the courier ones per
    service. Courier needs the point inside India (the bounding box)."""
    params = {"lat": lat, "lng": lng}
    local = tuple(
        int(r[0]) for r in (await session.execute(_LOCAL_STORES_SQL, params)).all()
    )
    courier: dict[int, list[int]] = {}
    if in_india_bbox(lat, lng):
        for store_id, service_id in (await session.execute(_COURIER_PAIRS_SQL, params)).all():
            courier.setdefault(int(service_id), []).append(int(store_id))
    return Locality(local=local, courier={k: tuple(v) for k, v in courier.items()})


_SHIPPING_SQL = text(
    "SELECT s.id, sps.service_id FROM store s "
    "JOIN sellerprofile_service sps ON sps.seller_profile_id = s.seller_profile_id "
    "  AND sps.courier_enabled "
    "WHERE s.id IN :store_ids ORDER BY s.id, sps.service_id"
).bindparams(bindparam("store_ids", expanding=True))


async def courier_enabled_service_ids(
    session: AsyncSession, store_ids: list[int]
) -> dict[int, tuple[int, ...]]:
    """Services with courier switched on, per store — for listing rows whose
    zone already established the ring and the payee."""
    if not store_ids:
        return {}
    rows = (await session.execute(_SHIPPING_SQL, {"store_ids": list(store_ids)})).all()
    out: dict[int, list[int]] = {}
    for store_id, service_id in rows:
        out.setdefault(int(store_id), []).append(int(service_id))
    return {k: tuple(v) for k, v in out.items()}
