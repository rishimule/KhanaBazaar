# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Unit tests for the pure rank_candidates helper. No DB."""
from app.schemas.price_comparison import ComparisonAlternative, ComparisonItem
from app.services.price_comparison import rank_candidates


def _alt(
    id: int,
    *,
    effective_total: float,
    distance_km: float,
    covered_count: int = 1,
    missing_count: int = 0,
) -> ComparisonAlternative:
    return ComparisonAlternative(
        id=id,
        name=f"Store {id}",
        distance_km=distance_km,
        covered_count=covered_count,
        missing_count=missing_count,
        covered_subtotal=effective_total,
        imputed_subtotal=0.0,
        effective_total=effective_total,
        items=[
            ComparisonItem(
                product_id=1,
                product_name="P",
                quantity=1,
                inventory_id=1,
                unit_price=effective_total,
                is_available=True,
                stock=10,
                line_total=effective_total,
                imputed=False,
                category_id=1,
            )
        ],
    )


def test_drops_zero_coverage_candidates() -> None:
    cands = [
        _alt(1, effective_total=100.0, distance_km=1.0, covered_count=0),
        _alt(2, effective_total=120.0, distance_km=2.0, covered_count=1),
    ]
    result = rank_candidates(cands)
    assert [a.id for a in result] == [2]


def test_sorts_by_effective_total_ascending() -> None:
    cands = [
        _alt(1, effective_total=150.0, distance_km=1.0),
        _alt(2, effective_total=120.0, distance_km=2.0),
        _alt(3, effective_total=130.0, distance_km=0.5),
    ]
    result = rank_candidates(cands)
    assert [a.id for a in result] == [2, 3]  # top 2


def test_tiebreak_by_distance_when_totals_equal() -> None:
    cands = [
        _alt(1, effective_total=100.0, distance_km=3.0),
        _alt(2, effective_total=100.0, distance_km=1.0),
        _alt(3, effective_total=100.0, distance_km=2.0),
    ]
    result = rank_candidates(cands)
    assert [a.id for a in result] == [2, 3]


def test_returns_at_most_two() -> None:
    cands = [
        _alt(i, effective_total=100.0 + i, distance_km=1.0) for i in range(5)
    ]
    result = rank_candidates(cands)
    assert len(result) == 2


def test_empty_input_returns_empty() -> None:
    assert rank_candidates([]) == []


def test_single_candidate_passes_through() -> None:
    cands = [_alt(1, effective_total=100.0, distance_km=1.0)]
    result = rank_candidates(cands)
    assert [a.id for a in result] == [1]
