# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Helpers for managing seller↔service junction rows and validating
incoming service_id payloads."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Service, ServiceTranslation
from app.models.profile import SellerProfile, SellerProfileService
from app.schemas.services import ServicePayload


async def validate_service_ids(
    session: AsyncSession, service_ids: list[int]
) -> list[int]:
    """Return deduped, ordered list of valid active service ids.

    Raises ValueError if any id is missing or inactive.
    """
    deduped = list(dict.fromkeys(service_ids))  # preserve order, drop dupes
    if not deduped:
        raise ValueError("service_ids must not be empty")
    result = await session.exec(
        select(Service.id).where(
            Service.id.in_(deduped),  # type: ignore[union-attr]
            Service.is_active == True,  # noqa: E712
        )
    )
    found = set(result.all())
    missing = [sid for sid in deduped if sid not in found]
    if missing:
        raise ValueError(f"unknown or inactive service_ids: {missing}")
    return deduped


async def replace_profile_services(
    session: AsyncSession, profile: SellerProfile, service_ids: list[int]
) -> None:
    """Replace a seller's service set atomically. Caller commits."""
    assert profile.id is not None
    existing_result = await session.exec(
        select(SellerProfileService).where(
            SellerProfileService.seller_profile_id == profile.id
        )
    )
    existing = {row.service_id: row for row in existing_result.all()}
    desired = set(service_ids)

    for service_id in desired - existing.keys():
        session.add(
            SellerProfileService(
                seller_profile_id=profile.id, service_id=service_id
            )
        )
    for service_id, row in list(existing.items()):
        if service_id not in desired:
            await session.delete(row)
    await session.flush()


async def list_profile_services(
    session: AsyncSession, seller_profile_id: int, language_code: str = "en"
) -> list[ServicePayload]:
    """Resolve a seller's services with translation, ordered by Service.sort_order."""
    grouped = await list_profile_services_for_many(
        session, [seller_profile_id], language_code=language_code
    )
    return grouped.get(seller_profile_id, [])


async def list_profile_services_for_many(
    session: AsyncSession,
    seller_profile_ids: list[int],
    language_code: str = "en",
) -> dict[int, list[ServicePayload]]:
    """Batched variant of list_profile_services keyed by seller_profile_id."""
    if not seller_profile_ids:
        return {}
    deduped = list(dict.fromkeys(seller_profile_ids))
    stmt = (
        select(
            SellerProfileService.seller_profile_id,
            Service,
            ServiceTranslation,
            SellerProfileService.min_order_value,
            SellerProfileService.delivery_eta_min_minutes,
            SellerProfileService.delivery_eta_max_minutes,
        )
        .join(
            SellerProfileService,
            SellerProfileService.service_id == Service.id,  # type: ignore[arg-type]
        )
        .join(
            ServiceTranslation,
            ServiceTranslation.service_id == Service.id,  # type: ignore[arg-type]
            isouter=True,
        )
        .where(SellerProfileService.seller_profile_id.in_(deduped))  # type: ignore[attr-defined]
        .where(
            (ServiceTranslation.language_code == language_code)
            | (ServiceTranslation.id.is_(None))  # type: ignore[union-attr]
        )
        .order_by(Service.sort_order, Service.id)  # type: ignore[arg-type]
    )
    result = await session.exec(stmt)
    grouped: dict[int, list[ServicePayload]] = {sid: [] for sid in deduped}
    for (
        profile_id,
        service,
        translation,
        min_order_value,
        eta_min,
        eta_max,
    ) in result.all():
        assert service.id is not None
        grouped.setdefault(profile_id, []).append(
            ServicePayload(
                id=service.id,
                created_at=service.created_at,
                updated_at=service.updated_at,
                slug=service.slug,
                name=translation.name if translation else service.slug,
                description=translation.description if translation else None,
                is_active=service.is_active,
                sort_order=service.sort_order,
                min_order_value=min_order_value,
                delivery_eta_min_minutes=eta_min,
                delivery_eta_max_minutes=eta_max,
            )
        )
    return grouped
