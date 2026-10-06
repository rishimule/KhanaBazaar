# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Search partitions local and courier results (spec §12, §16)."""
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.profile import SellerProfileService
from app.models.store import Store
from app.search.partition import fulfilment_rank, product_groups, store_groups
from app.search.reindex import reindex_all
from app.services.serviceability import Locality
from tests._courier_helpers import COURIER_POINT, FAR_POINT, LOCAL_POINT
from tests._discovery_helpers import seed_discovery_world


def test_product_groups_are_disjoint_and_local_first() -> None:
    groups = product_groups(Locality(local=(3,), courier={5: (7, 9)}))
    assert groups == [
        ("local", "store_ids IN [3]"),
        ("courier", "((service_id = 5 AND store_ids IN [7,9])) AND NOT store_ids IN [3]"),
    ]
    assert product_groups(Locality(courier={5: (7,)})) == [
        ("courier", "((service_id = 5 AND store_ids IN [7]))"),
    ]
    assert product_groups(Locality()) == []


def test_store_groups_keep_other_stores_last() -> None:
    assert store_groups(Locality(local=(3,), courier={5: (7,)})) == [
        ("local", "id IN [3]"), ("courier", "id IN [7]"), (None, "NOT id IN [3,7]"),
    ]
    assert store_groups(Locality()) == [(None, None)]


def test_fulfilment_rank() -> None:
    assert [fulfilment_rank(f) for f in ("local", "courier", None)] == [0, 1, 2]


async def _products(client: AsyncClient, point: tuple[float, float], **params: Any) -> dict[str, Any]:
    resp = await client.get(
        "/api/v1/search/products", params={"q": "", "lat": point[0], "lng": point[1], **params}
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


@pytest.mark.asyncio
async def test_products_lists_local_matches_then_courier_ones(
    client: AsyncClient, session: AsyncSession, meili_test_client: Any
) -> None:
    world = await seed_discovery_world(session)
    await reindex_all(session, meili_test_client)
    body = await _products(client, COURIER_POINT)
    assert [p["id"] for p in body["products"]] == [world.kaju_id, world.soan_id]
    assert body["total"] == 2
    # Kaju Katli is counted by the local query, Soan Papdi by the courier one.
    assert body["facets"]["service_id"] == {str(world.service_id): 2}
    kaju, soan = body["products"]
    assert [
        (o["store_id"], o["fulfilment"], o["is_serviceable"]) for o in kaju["per_store_offers"]
    ] == [
        (world.mysuru_store_id, "local", True),
        (world.ravi_store_id, "courier", True),
        (world.mira_store_id, None, False),
    ]
    assert [(o["store_id"], o["fulfilment"]) for o in soan["per_store_offers"]] == [
        (world.ravi_store_id, "courier"),
    ]


@pytest.mark.asyncio
async def test_products_page_window_crosses_the_group_boundary(
    client: AsyncClient, session: AsyncSession, meili_test_client: Any
) -> None:
    world = await seed_discovery_world(session)
    await reindex_all(session, meili_test_client)
    pages = [await _products(client, COURIER_POINT, page=n, page_size=1) for n in (1, 2, 3)]
    # Each product exactly once across the pages, local first; then an empty page.
    assert [p["id"] for page in pages for p in page["products"]] == [world.kaju_id, world.soan_id]
    assert pages[2]["products"] == []
    assert {page["total"] for page in pages} == {2}


@pytest.mark.asyncio
async def test_products_without_courier_or_out_of_range(
    client: AsyncClient, session: AsyncSession, meili_test_client: Any
) -> None:
    world = await seed_discovery_world(session)
    sps = await session.get(SellerProfileService, world.courier.sps_id)
    assert sps is not None
    sps.courier_enabled = False
    await session.commit()
    await reindex_all(session, meili_test_client)
    mysuru = await _products(client, COURIER_POINT)
    assert [p["id"] for p in mysuru["products"]] == [world.kaju_id]
    delhi = await _products(client, FAR_POINT)
    assert delhi["total"] == 0 and delhi["products"] == []
    home = await _products(client, LOCAL_POINT)
    assert {p["id"] for p in home["products"]} == {world.kaju_id, world.soan_id}


@pytest.mark.asyncio
async def test_store_scoped_search_is_unchanged(
    client: AsyncClient, session: AsyncSession, meili_test_client: Any
) -> None:
    world = await seed_discovery_world(session)
    await reindex_all(session, meili_test_client)
    resp = await client.get(
        "/api/v1/search/products", params={"q": "", "store_id": world.ravi_store_id}
    )
    body = resp.json()
    assert {p["id"] for p in body["products"]} == {world.kaju_id, world.soan_id}
    for product in body["products"]:
        for offer in product["per_store_offers"]:
            assert offer["is_serviceable"] is (offer["store_id"] == world.ravi_store_id)
            assert offer["fulfilment"] is None


@pytest.mark.asyncio
async def test_suggest_fills_with_courier_products_and_orders_stores(
    client: AsyncClient, session: AsyncSession, meili_test_client: Any
) -> None:
    world = await seed_discovery_world(session)
    await reindex_all(session, meili_test_client)
    lat, lng = COURIER_POINT
    papdi = (await client.get(
        "/api/v1/search/suggest", params={"q": "papdi", "lat": lat, "lng": lng}
    )).json()
    assert [p["id"] for p in papdi["products"]] == [world.soan_id]
    assert papdi["products"][0]["best_store"]["id"] == world.ravi_store_id
    kaju = (await client.get(
        "/api/v1/search/suggest", params={"q": "kaju", "lat": lat, "lng": lng}
    )).json()
    # Only the stores that reach Mysuru count: Mysuru Mart (local), Ravi (courier).
    assert kaju["products"][0]["store_count"] == 2
    marts = (await client.get(
        "/api/v1/search/suggest", params={"q": "mart", "lat": lat, "lng": lng}
    )).json()
    assert [(s["name"], s["fulfilment"]) for s in marts["stores"]] == [
        ("Mysuru Mart", "local"), ("Mira Mart", None),
    ]


@pytest.mark.asyncio
async def test_store_name_search_pages_local_courier_then_others(
    client: AsyncClient, session: AsyncSession, meili_test_client: Any
) -> None:
    world = await seed_discovery_world(session)
    # The stores index searches names only, so give all three a shared word.
    for store_id, name in (
        (world.ravi_store_id, "Ravi Bazaar"),
        (world.mira_store_id, "Mira Bazaar"),
        (world.mysuru_store_id, "Mysuru Bazaar"),
    ):
        store = await session.get(Store, store_id)
        assert store is not None
        store.name = name
    await session.commit()
    await reindex_all(session, meili_test_client)
    lat, lng = COURIER_POINT
    seen: list[tuple[str, str | None]] = []
    for page in (1, 2, 3):
        resp = await client.get(
            "/api/v1/search/stores",
            params={"q": "bazaar", "lat": lat, "lng": lng, "page": page, "page_size": 1},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 3
        seen += [(s["name"], s["fulfilment"]) for s in body["stores"]]
    assert seen == [
        ("Mysuru Bazaar", "local"), ("Ravi Bazaar", "courier"), ("Mira Bazaar", None),
    ]
    anywhere = (await client.get("/api/v1/search/stores", params={"q": "bazaar"})).json()
    assert anywhere["total"] == 3
    assert {s["fulfilment"] for s in anywhere["stores"]} == {None}


@pytest.mark.asyncio
async def test_browse_fills_carousels_with_courier_products(
    client: AsyncClient, session: AsyncSession, meili_test_client: Any
) -> None:
    world = await seed_discovery_world(session)
    await reindex_all(session, meili_test_client)
    lat, lng = COURIER_POINT
    body = (await client.get(
        "/api/v1/search/browse", params={"service_id": world.service_id, "lat": lat, "lng": lng}
    )).json()
    [category] = body["categories"]
    assert [p["id"] for p in category["products"]] == [world.kaju_id, world.soan_id]
    assert [s["slug"] for s in category["subcategories"]] == ["barfi"]
    delhi = (await client.get(
        "/api/v1/search/browse",
        params={"service_id": world.service_id, "lat": FAR_POINT[0], "lng": FAR_POINT[1]},
    )).json()
    assert delhi["categories"] == []


@pytest.mark.asyncio
async def test_compare_orders_local_then_courier_then_unreachable(
    client: AsyncClient, session: AsyncSession
) -> None:
    world = await seed_discovery_world(session)
    lat, lng = COURIER_POINT
    body = (await client.get(
        f"/api/v1/search/products/{world.kaju_id}/stores", params={"lat": lat, "lng": lng}
    )).json()
    assert [
        (o["store"]["name"], o["fulfilment"], o["is_serviceable"]) for o in body["offers"]
    ] == [
        ("Mysuru Mart", "local", True),    # ₹120
        ("Ravi Sweets", "courier", True),  # ₹100
        ("Mira Mart", None, False),        # ₹90 — cheapest, but can't reach Mysuru
    ]
    card_offers = {o["store_id"]: o["fulfilment"] for o in body["product"]["per_store_offers"]}
    assert card_offers[world.ravi_store_id] == "courier"
    anywhere = (await client.get(f"/api/v1/search/products/{world.kaju_id}/stores")).json()
    assert [o["store"]["name"] for o in anywhere["offers"]] == [
        "Mira Mart", "Ravi Sweets", "Mysuru Mart",
    ]  # price order, as before
    assert {o["fulfilment"] for o in anywhere["offers"]} == {None}
