# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Coverage for the batched translation loaders + pick_translation helper.

Per-row translation lookups in catalog list endpoints used to be N+1.
Batched helpers fix that by pulling every translation for a list of ids
in one query.
"""

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Service, ServiceTranslation
from app.services.catalog_translations import (
    load_service_translations,
    pick_translation,
)


@pytest.mark.asyncio
async def test_load_service_translations_returns_map_by_service_id(
    session: AsyncSession,
) -> None:
    svc = Service(slug="grocery-batched", is_active=True, sort_order=0)
    session.add(svc)
    await session.flush()
    assert svc.id is not None
    svc_id = svc.id
    session.add(ServiceTranslation(service_id=svc_id, language_code="en", name="Grocery"))
    session.add(ServiceTranslation(service_id=svc_id, language_code="hi", name="किराना"))
    await session.commit()

    out = await load_service_translations(session, [svc_id])
    assert svc_id in out
    by_lang = {t.language_code: t.name for t in out[svc_id]}
    assert by_lang["en"] == "Grocery"
    assert by_lang["hi"] == "किराना"


@pytest.mark.asyncio
async def test_load_service_translations_empty_input_returns_empty_map(
    session: AsyncSession,
) -> None:
    out = await load_service_translations(session, [])
    assert out == {}


def test_pick_translation_returns_requested_lang_when_present() -> None:
    translations = [
        ServiceTranslation(service_id=1, language_code="en", name="Grocery"),
        ServiceTranslation(service_id=1, language_code="hi", name="किराना"),
    ]
    chosen = pick_translation(translations, "hi")
    assert chosen is not None
    assert chosen.name == "किराना"


def test_pick_translation_falls_back_to_english() -> None:
    translations = [
        ServiceTranslation(service_id=1, language_code="en", name="Grocery"),
    ]
    chosen = pick_translation(translations, "hi")
    assert chosen is not None
    assert chosen.language_code == "en"


def test_pick_translation_returns_none_when_no_translations() -> None:
    assert pick_translation([], "hi") is None


def test_pick_translation_returns_none_when_neither_requested_nor_english() -> None:
    translations = [ServiceTranslation(service_id=1, language_code="hi", name="किराना")]
    assert pick_translation(translations, "mr") is None
