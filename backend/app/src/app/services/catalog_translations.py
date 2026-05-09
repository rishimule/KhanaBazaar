# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Localized translation lookups for catalog entities.

All helpers fall back to English when a translation is missing for the
requested language code, matching the behavior previously inlined in
api/catalog.py.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import (
    CategoryTranslation,
    LanguageCode,
    MasterProductTranslation,
    ServiceTranslation,
    SubcategoryTranslation,
)

_EN = LanguageCode.English.value


async def localized_service_translation(
    session: AsyncSession, service_id: int, lang: str
) -> ServiceTranslation | None:
    if lang != _EN:
        result = await session.exec(
            select(ServiceTranslation).where(
                ServiceTranslation.service_id == service_id,
                ServiceTranslation.language_code == lang,
            )
        )
        row = result.first()
        if row is not None:
            return row
    result = await session.exec(
        select(ServiceTranslation).where(
            ServiceTranslation.service_id == service_id,
            ServiceTranslation.language_code == _EN,
        )
    )
    return result.first()


async def localized_category_translation(
    session: AsyncSession, category_id: int, lang: str
) -> CategoryTranslation | None:
    if lang != _EN:
        result = await session.exec(
            select(CategoryTranslation).where(
                CategoryTranslation.category_id == category_id,
                CategoryTranslation.language_code == lang,
            )
        )
        row = result.first()
        if row is not None:
            return row
    result = await session.exec(
        select(CategoryTranslation).where(
            CategoryTranslation.category_id == category_id,
            CategoryTranslation.language_code == _EN,
        )
    )
    return result.first()


async def localized_subcategory_translation(
    session: AsyncSession, subcategory_id: int, lang: str
) -> SubcategoryTranslation | None:
    if lang != _EN:
        result = await session.exec(
            select(SubcategoryTranslation).where(
                SubcategoryTranslation.subcategory_id == subcategory_id,
                SubcategoryTranslation.language_code == lang,
            )
        )
        row = result.first()
        if row is not None:
            return row
    result = await session.exec(
        select(SubcategoryTranslation).where(
            SubcategoryTranslation.subcategory_id == subcategory_id,
            SubcategoryTranslation.language_code == _EN,
        )
    )
    return result.first()


async def localized_product_translation(
    session: AsyncSession, product_id: int, lang: str
) -> MasterProductTranslation | None:
    if lang != _EN:
        result = await session.exec(
            select(MasterProductTranslation).where(
                MasterProductTranslation.master_product_id == product_id,
                MasterProductTranslation.language_code == lang,
            )
        )
        row = result.first()
        if row is not None:
            return row
    result = await session.exec(
        select(MasterProductTranslation).where(
            MasterProductTranslation.master_product_id == product_id,
            MasterProductTranslation.language_code == _EN,
        )
    )
    return result.first()
