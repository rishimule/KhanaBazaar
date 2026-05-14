# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Localized translation lookups for catalog entities.

Two flavors:
- Per-entity helpers (`localized_*_translation`) — single-row lookup with
  English fallback. Kept for compatibility with existing call sites.
- Batched helpers (`load_*_translations`) — bulk load all translations for
  a list of entity ids. Pair with `pick_translation` to localize each row.
  Prefer these in any new code that iterates a result set.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import TypeVar, cast

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

T = TypeVar("T")


def pick_translation(translations: Sequence[T], lang: str) -> T | None:
    """Pick the requested-language translation from a pre-loaded list, falling back to English."""
    en_match: T | None = None
    for row in translations:
        code = cast(str, row.language_code)  # type: ignore[attr-defined]
        if code == lang:
            return row
        if code == _EN:
            en_match = row
    return en_match


async def load_service_translations(
    session: AsyncSession, service_ids: Iterable[int]
) -> dict[int, list[ServiceTranslation]]:
    ids = list({i for i in service_ids if i is not None})
    if not ids:
        return {}
    result = await session.exec(
        select(ServiceTranslation).where(ServiceTranslation.service_id.in_(ids))  # type: ignore[attr-defined]
    )
    grouped: dict[int, list[ServiceTranslation]] = defaultdict(list)
    for row in result.all():
        grouped[row.service_id].append(row)
    return grouped


async def load_category_translations(
    session: AsyncSession, category_ids: Iterable[int]
) -> dict[int, list[CategoryTranslation]]:
    ids = list({i for i in category_ids if i is not None})
    if not ids:
        return {}
    result = await session.exec(
        select(CategoryTranslation).where(CategoryTranslation.category_id.in_(ids))  # type: ignore[attr-defined]
    )
    grouped: dict[int, list[CategoryTranslation]] = defaultdict(list)
    for row in result.all():
        grouped[row.category_id].append(row)
    return grouped


async def load_subcategory_translations(
    session: AsyncSession, subcategory_ids: Iterable[int]
) -> dict[int, list[SubcategoryTranslation]]:
    ids = list({i for i in subcategory_ids if i is not None})
    if not ids:
        return {}
    result = await session.exec(
        select(SubcategoryTranslation).where(
            SubcategoryTranslation.subcategory_id.in_(ids)  # type: ignore[attr-defined]
        )
    )
    grouped: dict[int, list[SubcategoryTranslation]] = defaultdict(list)
    for row in result.all():
        grouped[row.subcategory_id].append(row)
    return grouped


async def load_product_translations(
    session: AsyncSession, product_ids: Iterable[int]
) -> dict[int, list[MasterProductTranslation]]:
    ids = list({i for i in product_ids if i is not None})
    if not ids:
        return {}
    result = await session.exec(
        select(MasterProductTranslation).where(
            MasterProductTranslation.master_product_id.in_(ids)  # type: ignore[attr-defined]
        )
    )
    grouped: dict[int, list[MasterProductTranslation]] = defaultdict(list)
    for row in result.all():
        grouped[row.master_product_id].append(row)
    return grouped


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
