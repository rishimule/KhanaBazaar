# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Read/upsert helpers for platform-fee configuration.

Getters never write. `get_or_create_*` are for the PATCH/PUT paths only, so a
GET can't spawn rows as a side effect."""
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform_fee import (
    PlatformFeeSettings,
    ServiceFeeConfig,
    ServiceSubscriptionPlan,
)

ALLOWED_DURATIONS = (3, 6, 12)


async def load_settings(session: AsyncSession) -> PlatformFeeSettings:
    """The single settings row, or a transient default (unsaved) if none yet."""
    row = (
        await session.exec(
            select(PlatformFeeSettings).order_by(PlatformFeeSettings.id).limit(1)  # type: ignore[arg-type]
        )
    ).first()
    return row or PlatformFeeSettings()


async def get_or_create_settings(session: AsyncSession) -> PlatformFeeSettings:
    row = (
        await session.exec(
            select(PlatformFeeSettings).order_by(PlatformFeeSettings.id).limit(1)  # type: ignore[arg-type]
        )
    ).first()
    if row is None:
        row = PlatformFeeSettings()
        session.add(row)
        await session.flush()
    return row


async def load_service_config(session: AsyncSession, service_id: int) -> ServiceFeeConfig:
    row = (
        await session.exec(
            select(ServiceFeeConfig).where(ServiceFeeConfig.service_id == service_id)
        )
    ).first()
    return row or ServiceFeeConfig(service_id=service_id)


async def get_or_create_service_config(
    session: AsyncSession, service_id: int
) -> ServiceFeeConfig:
    row = (
        await session.exec(
            select(ServiceFeeConfig).where(ServiceFeeConfig.service_id == service_id)
        )
    ).first()
    if row is None:
        row = ServiceFeeConfig(service_id=service_id)
        session.add(row)
        await session.flush()
    return row


async def list_plans(
    session: AsyncSession, service_id: int
) -> list[ServiceSubscriptionPlan]:
    return list(
        (
            await session.exec(
                select(ServiceSubscriptionPlan)
                .where(ServiceSubscriptionPlan.service_id == service_id)
                .order_by(ServiceSubscriptionPlan.duration_months)  # type: ignore[arg-type]
            )
        ).all()
    )
