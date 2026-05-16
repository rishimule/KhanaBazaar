# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Meilisearch index settings + synonyms + version."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

SETTINGS_VERSION = 1

_SYNONYMS_PATH = Path(__file__).parent / "synonyms.json"


def load_synonyms() -> dict[str, list[str]]:
    return json.loads(_SYNONYMS_PATH.read_text(encoding="utf-8"))


def products_index_settings() -> dict[str, Any]:
    return {
        "searchableAttributes": [
            "name_en", "name_hi", "name_mr", "name_gu", "name_pa",
            "brand",
            "category_name_en", "subcategory_name_en",
            "description_en", "description_hi", "description_mr",
            "description_gu", "description_pa",
        ],
        "filterableAttributes": [
            "is_active", "service_id", "category_id", "subcategory_id",
            "store_ids", "min_price", "max_price", "in_stock_anywhere", "brand",
        ],
        "sortableAttributes": ["min_price", "updated_at"],
        "rankingRules": [
            "words", "typo", "proximity", "attribute", "exactness",
            "in_stock_anywhere:desc", "updated_at:desc",
        ],
        "typoTolerance": {
            "minWordSizeForTypos": {"oneTypo": 4, "twoTypos": 7}
        },
        "synonyms": load_synonyms(),
        "stopWords": ["the", "a", "an"],
    }


def stores_index_settings() -> dict[str, Any]:
    return {
        "searchableAttributes": ["name"],
        "filterableAttributes": ["service_ids", "is_active"],
        "sortableAttributes": [],
        "rankingRules": ["words", "typo", "proximity", "attribute", "exactness"],
    }


def search_terms_index_settings() -> dict[str, Any]:
    return {
        "searchableAttributes": ["term"],
        "filterableAttributes": ["locale", "kind"],
        "sortableAttributes": ["weight"],
        "rankingRules": [
            "words", "typo", "proximity", "attribute", "exactness", "weight:desc",
        ],
    }


INDEX_SETTINGS: dict[str, Callable[[], dict[str, Any]]] = {
    "products": products_index_settings,
    "stores": stores_index_settings,
    "search_terms": search_terms_index_settings,
}
