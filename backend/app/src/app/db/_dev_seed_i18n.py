# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Non-English seed translations (hi, mr, gu, pa) for the dev catalog.

English copy lives inline in ``dev_seed.py`` / ``_dev_seed_data.py``; this module
layers the other four locales on top so the dev DB exercises the multilingual
catalog end to end.

Sources:
- ``i18n/<lang>.json`` — hand-curated translations for every service, category,
  subcategory, and the 135 hand-written *anchor* products, plus a brand
  transliteration map and per-subcategory ``noun``/``variants`` translations.
- The 1,365 *generated* products are not translated one by one. They are rebuilt
  from building blocks using ``_dev_seed_data.EXTRA_PRODUCT_META`` so the localized
  name mirrors the English template exactly:
      name        = f"{brand_t} {noun_t} ({variant_t})"
      description  = f"{name_t} — {sub_description_t}"

Public maps are keyed ``slug -> {lang: {"name": ..., "description": ...}}`` and
cover the *non-English* locales only (English is written by the seed directly).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db._dev_seed_data import EXTRA_PRODUCT_META

LANGS: tuple[str, ...] = ("hi", "mr", "gu", "pa")

_I18N_DIR = Path(__file__).parent / "i18n"

# lang -> raw translation document loaded from disk.
_RAW: dict[str, dict[str, Any]] = {}
for _lang in LANGS:
    _path = _I18N_DIR / f"{_lang}.json"
    if not _path.exists():  # pragma: no cover - guards a broken checkout
        raise FileNotFoundError(
            f"missing seed translation file {_path}; expected one JSON per locale in {LANGS}"
        )
    with _path.open(encoding="utf-8") as _fh:
        _RAW[_lang] = json.load(_fh)


def _by_slug(section: str) -> dict[str, dict[str, dict[str, str]]]:
    """Pivot ``{lang: {slug: {name, description}}}`` into ``{slug: {lang: {...}}}``."""
    out: dict[str, dict[str, dict[str, str]]] = {}
    for lang in LANGS:
        for slug, fields in _RAW[lang][section].items():
            out.setdefault(slug, {})[lang] = {
                "name": fields["name"],
                "description": fields["description"],
            }
    return out


SERVICE_I18N: dict[str, dict[str, dict[str, str]]] = _by_slug("services")
CATEGORY_I18N: dict[str, dict[str, dict[str, str]]] = _by_slug("categories")
SUBCATEGORY_I18N: dict[str, dict[str, dict[str, str]]] = _by_slug("subcategories")


def _build_product_i18n() -> dict[str, dict[str, dict[str, str]]]:
    """All product translations: anchor products verbatim from JSON, generated
    products rebuilt from translated brand + subcategory noun/variant/description."""
    out: dict[str, dict[str, dict[str, str]]] = _by_slug("anchor_products")

    for slug, meta in EXTRA_PRODUCT_META.items():
        sub_slug = meta["subcategory_slug"]
        brand = meta["brand"]
        variant_index = meta["variant_index"]
        for lang in LANGS:
            sub_t = _RAW[lang]["subcategories"][sub_slug]
            brand_t = _RAW[lang]["brands"][brand]
            noun_t = sub_t["noun"]
            variant_t = sub_t["variants"][variant_index]
            name_t = f"{brand_t} {noun_t} ({variant_t})"
            out.setdefault(slug, {})[lang] = {
                "name": name_t,
                "description": f"{name_t} — {sub_t['description']}",
            }
    return out


PRODUCT_I18N: dict[str, dict[str, dict[str, str]]] = _build_product_i18n()
