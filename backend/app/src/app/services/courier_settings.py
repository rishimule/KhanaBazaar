# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Validation for the courier seller settings (spec 2026-10-02 §7).

Shared by the direct write paths (pending sellers, admins) and the change
request create/approve paths, so every route enforces the same rules.
"""
from __future__ import annotations

from fastapi import HTTPException

from app.core.config import settings
from app.models.profile import SellerProfile


def resolve_courier_radius(current: float | None, proposed: float | None) -> float | None:
    """`None` keeps the current value, `0` turns courier off, else sets it."""
    if proposed is None:
        return current
    if proposed == 0:
        return None
    return float(proposed)


def assert_courier_radius(
    local_km: float, courier_km: float | None, *, current_km: float | None = None
) -> None:
    """A courier ring, when set, must be larger than the local radius and
    within the configured cap. The cap binds only a ring that differs from the
    stored one (`current_km`): lowering COURIER_MAX_RADIUS_KM must never block
    an unrelated edit — a pin confirmation, or a local-radius change whose
    pre-filled form re-sends the existing ring unchanged."""
    if courier_km is None:
        return
    if courier_km <= local_km:
        raise HTTPException(status_code=422, detail="courier_radius_not_larger")
    if courier_km != current_km and courier_km > settings.COURIER_MAX_RADIUS_KM:
        raise HTTPException(status_code=422, detail="courier_radius_too_large")


def apply_bank_fields(
    profile: SellerProfile, *, name: str | None, enabled: bool | None
) -> None:
    """Omitted means unchanged (a stale client must not wipe them); "" clears
    the account name."""
    if name is not None:
        profile.bank_account_name = name.strip() or None
    if enabled is not None:
        profile.bank_transfer_enabled = enabled


def assert_bank_transfer_complete(profile: SellerProfile) -> None:
    """Bank transfer may be on only with name, number and IFSC all present."""
    if profile.bank_transfer_enabled and not (
        profile.bank_account_name and profile.bank_account_number and profile.bank_ifsc
    ):
        raise HTTPException(status_code=422, detail="bank_transfer_incomplete")
