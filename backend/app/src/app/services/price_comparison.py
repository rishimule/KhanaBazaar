# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Price comparison service.

`rank_candidates` is a pure function (no DB) -- easily unit tested.
`find_alternatives` is the session-bound entrypoint that builds candidates
from PostGIS + inventory data, then delegates ranking to `rank_candidates`.
"""
from app.schemas.price_comparison import ComparisonAlternative

MAX_ALTERNATIVES = 2


def rank_candidates(
    candidates: list[ComparisonAlternative],
) -> list[ComparisonAlternative]:
    """Drop zero-coverage stores, sort by (effective_total ASC, distance_km
    ASC), return top MAX_ALTERNATIVES."""
    eligible = [c for c in candidates if c.covered_count > 0]
    eligible.sort(key=lambda c: (c.effective_total, c.distance_km))
    return eligible[:MAX_ALTERNATIVES]
