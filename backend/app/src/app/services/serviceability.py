# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Which zone a location falls in for a store: local, courier, or none.

The single home of the delivery-radius rule (spec 2026-10-02 §5). Availability
— store paused, service paused, fee suspended — is deliberately NOT part of a
zone: checkout and the listings already enforce those with their own messages,
so a paused store keeps showing its pause banner instead of "out of range".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.commerce import PaymentMethod
from app.models.profile import SellerProfile, SellerProfileService
from app.models.store import Store
from app.search.locality import in_india_bbox

Zone = Literal["local", "courier", "none"]

_INDIA_PIN_RE = re.compile(r"^[1-9]\d{5}$")


@dataclass(frozen=True)
class StoreZone:
    zone: Zone
    distance_km: float | None = None
    # Services that can ship by courier to this point; empty unless "courier".
    courier_service_ids: tuple[int, ...] = ()


def bank_transfer_live(seller: SellerProfile) -> bool:
    """Bank transfer counts only when switched on AND fully specified."""
    return bool(
        seller.bank_transfer_enabled
        and seller.bank_account_name
        and seller.bank_account_number
        and seller.bank_ifsc
    )


def courier_payment_methods(seller: SellerProfile) -> list[PaymentMethod]:
    """Prepaid methods a courier customer can pay this seller by, UPI first."""
    methods: list[PaymentMethod] = []
    if seller.upi_enabled and seller.upi_vpa:
        methods.append(PaymentMethod.Upi)
    if bank_transfer_live(seller):
        methods.append(PaymentMethod.NetBanking)
    return methods


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


_POINT = "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography"
_ZONE_SQL = text(
    f"SELECT ST_Distance(a.geo, {_POINT}) / 1000.0 AS distance_km, "
    f"  ST_DWithin(a.geo, {_POINT}, s.delivery_radius_km * 1000) AS in_local, "
    f"  COALESCE(ST_DWithin(a.geo, {_POINT}, s.courier_radius_km * 1000), false) AS in_courier "
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
