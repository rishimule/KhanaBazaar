# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Local-first search (spec 2026-10-02 §12).

Results are split into disjoint groups — products a local store sells, then
products only a courier store ships — and each group is a separate
Meilisearch query. `stitched_search` places one page window across the
groups in order, using exact per-group totals.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Optional

from meilisearch_python_sdk.models.search import SearchParams

from app.services.serviceability import Fulfilment, Locality

_RANK = {"local": 0, "courier": 1}


def fulfilment_rank(fulfilment: Optional[str]) -> int:
    """Sort key for "local, then courier, then can't reach"."""
    return _RANK.get(fulfilment or "", 2)


def ids_in(field: str, ids: Iterable[int]) -> str:
    return f"{field} IN [{','.join(str(int(i)) for i in ids)}]"


def product_groups(locality: Locality) -> list[tuple[Fulfilment, str]]:
    """① a local store sells it; ② no local store does, and a courier store
    ships it for its own service. Empty when nothing serves the point."""
    groups: list[tuple[Fulfilment, str]] = []
    if locality.local:
        groups.append(("local", ids_in("store_ids", locality.local)))
    if locality.courier:
        ships = " OR ".join(
            f"(service_id = {int(service_id)} AND {ids_in('store_ids', stores)})"
            for service_id, stores in sorted(locality.courier.items())
        )
        clause = f"({ships})"
        if locality.local:
            clause += f" AND NOT {ids_in('store_ids', locality.local)}"
        groups.append(("courier", clause))
    return groups


def store_groups(locality: Locality) -> list[tuple[Optional[Fulfilment], Optional[str]]]:
    """Store-index groups: local, courier, then every other store (a name
    search still finds a far store). A None filter means "no extra filter"."""
    served = sorted(set(locality.local) | locality.courier_store_ids)
    if not served:
        return [(None, None)]
    groups: list[tuple[Optional[Fulfilment], Optional[str]]] = []
    if locality.local:
        groups.append(("local", ids_in("id", locality.local)))
    courier_only = sorted(locality.courier_store_ids - set(locality.local))
    if courier_only:
        groups.append(("courier", ids_in("id", courier_only)))
    groups.append((None, f"NOT {ids_in('id', served)}"))
    return groups


def combine(base: str, extra: Optional[str]) -> str:
    return f"{base} AND ({extra})" if extra else base


@dataclass(frozen=True)
class Stitched:
    hits: list[tuple[int, dict[str, Any]]]  # (group index, hit)
    total: int
    facets: dict[str, dict[str, int]]


async def stitched_search(
    client: Any,
    index_uid: str,
    query: str,
    *,
    base_filter: str,
    group_filters: list[Optional[str]],
    offset: int,
    limit: int,
    sort: Optional[list[str]] = None,
    facets: Optional[list[str]] = None,
    attributes_to_retrieve: Optional[list[str]] = None,
) -> Stitched:
    """One page across groups searched in order: every match of group 1, then
    group 2, ... Facet counts are summed over the groups."""
    counts = await client.multi_search([
        SearchParams(
            index_uid=index_uid, query=query, filter=combine(base_filter, group),
            page=1, hits_per_page=0, facets=facets,
        )
        for group in group_filters
    ])
    totals = [int(r.total_hits or 0) for r in counts]
    # The SDK defaults attributes_to_retrieve to ["*"] and rejects None.
    projection: dict[str, Any] = (
        {} if attributes_to_retrieve is None
        else {"attributes_to_retrieve": attributes_to_retrieve}
    )
    window: list[SearchParams] = []
    slots: list[int] = []
    start, remaining = offset, limit
    for index, total in enumerate(totals):
        if remaining <= 0:
            break
        if start >= total:
            start -= total
            continue
        take = min(remaining, total - start)
        window.append(
            SearchParams(
                index_uid=index_uid, query=query,
                filter=combine(base_filter, group_filters[index]),
                offset=start, limit=take, sort=sort, **projection,
            )
        )
        slots.append(index)
        remaining -= take
        start = 0
    pages = await client.multi_search(window) if window else []
    hits = [(slot, hit) for slot, page in zip(slots, pages, strict=True) for hit in page.hits]
    summed: dict[str, dict[str, int]] = {}
    for result in counts:
        for name, distribution in (result.facet_distribution or {}).items():
            bucket = summed.setdefault(name, {})
            for value, count in distribution.items():
                bucket[str(value)] = bucket.get(str(value), 0) + int(count)
    return Stitched(hits=hits, total=sum(totals), facets=summed)
