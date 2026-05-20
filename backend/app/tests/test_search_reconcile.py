# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Unit tests for the reconciler diff core. Orchestration tests live in
test_search_reconcile_integration.py once Task 5 lands.
"""
from __future__ import annotations

from app.search.reconcile import (
    COMPARE_FIELDS_PRODUCT,
    ShardDeltas,
    current_shard,
    diff_shard,
    total_deltas,
)


def test_diff_detects_missing_in_meili() -> None:
    db = {1: {"name_en": "A", "db_updated_at": 10}}
    meili: dict = {}
    deltas = diff_shard(db, meili, COMPARE_FIELDS_PRODUCT)
    assert deltas.missing == [1]
    assert deltas.modified == []
    assert deltas.extra == []


def test_diff_detects_modified_field() -> None:
    db = {1: {"name_en": "A", "db_updated_at": 11}}
    meili = {1: {"name_en": "A", "db_updated_at": 10}}
    deltas = diff_shard(db, meili, COMPARE_FIELDS_PRODUCT)
    assert deltas.modified == [1]
    assert deltas.missing == []
    assert deltas.extra == []


def test_diff_ignores_fields_not_in_compare_list() -> None:
    db = {1: {"name_en": "A", "db_updated_at": 10, "image_url": "x"}}
    meili = {1: {"name_en": "A", "db_updated_at": 10, "image_url": "y"}}
    deltas = diff_shard(db, meili, COMPARE_FIELDS_PRODUCT)
    assert deltas.modified == []


def test_diff_detects_meili_extra() -> None:
    db: dict = {}
    meili = {99: {"name_en": "Z", "db_updated_at": 5}}
    deltas = diff_shard(db, meili, COMPARE_FIELDS_PRODUCT)
    assert deltas.extra == [99]
    assert deltas.missing == []


def test_diff_handles_multi_locale_drift() -> None:
    db = {7: {"name_en": "A", "name_hi": "अ", "db_updated_at": 10}}
    meili = {7: {"name_en": "A", "name_hi": "B", "db_updated_at": 10}}
    deltas = diff_shard(db, meili, COMPARE_FIELDS_PRODUCT)
    assert deltas.modified == [7]


def test_diff_returns_sorted_ids() -> None:
    db = {3: {"name_en": "A"}, 1: {"name_en": "B"}, 2: {"name_en": "C"}}
    meili: dict = {}
    deltas = diff_shard(db, meili, COMPARE_FIELDS_PRODUCT)
    assert deltas.missing == [1, 2, 3]


def test_total_deltas_sums_partitions() -> None:
    deltas = ShardDeltas(missing=[1, 2], modified=[3], extra=[4, 5, 6])
    assert total_deltas(deltas) == 6


def test_current_shard_cycles_every_24h() -> None:
    base = 0.0
    shards = {current_shard(base + h * 3600) for h in range(24)}
    assert shards == set(range(24))
    assert current_shard(base) == current_shard(base + 24 * 3600)
