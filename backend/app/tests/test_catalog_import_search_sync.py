# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Meilisearch sync during a bulk import rides on the standard hook.

An earlier draft of the importer suppressed `search.hooks` and enqueued
`reindex_products_by_subcategory` once per touched subcategory, on the
assumption that it was a bulk indexer. It is not — it is a **fan-out
dispatcher** (`search/tasks.py:270`) that enqueues one `reindex_master_product`
per product in the whole subcategory. That made the "optimization" strictly
worse: touching 3 products in a 500-product subcategory would have enqueued 500
tasks where the hook enqueues 3.

These tests pin the behaviour that matters: sync is **proportional to what
changed**, and it reaches products whose ancestors were renamed.

`conftest._stub_search_celery_delays` no-ops these `.delay()`s for the whole
suite; the inner `patch()` here overrides that stub for the with-block, which
is the documented way to assert on them.
"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Category, MasterProduct, Subcategory
from tests.catalog_csv_fixtures import IMPORTS, row, upload

pytestmark = pytest.mark.asyncio


async def test_sync_is_proportional_to_the_products_touched(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    rows = [row(product_slug=f"p-{i:03d}") for i in range(12)]
    created = await upload(client, admin_auth_headers, rows)
    job_id = created.json()["id"]

    with patch("app.search.tasks.reindex_master_product.delay") as per_product:
        applied = await client.post(
            f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers
        )
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"

    products = (await session.exec(select(MasterProduct))).all()
    assert len(products) == 12
    # Deduped by product id per commit, so exactly the 12 created products.
    enqueued = {call.args[0] for call in per_product.call_args_list}
    assert enqueued == {p.id for p in products}


async def test_untouched_products_are_not_reindexed(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """The regression the removed "batching" would have caused: a second import
    touching one product must not re-index the other nine in its subcategory."""
    await_first = await upload(
        client,
        admin_auth_headers,
        [row(product_slug=f"p-{i}") for i in range(10)],
    )
    await client.post(
        f"{IMPORTS}/{await_first.json()['id']}/apply", headers=admin_auth_headers
    )

    second = await upload(
        client, admin_auth_headers, [row(product_slug="p-3", base_price="99")]
    )
    with patch("app.search.tasks.reindex_master_product.delay") as per_product:
        await client.post(
            f"{IMPORTS}/{second.json()['id']}/apply", headers=admin_auth_headers
        )

    target = (
        await session.exec(select(MasterProduct).where(MasterProduct.slug == "p-3"))
    ).first()
    assert target is not None
    enqueued = {call.args[0] for call in per_product.call_args_list}
    assert enqueued == {target.id}, "only the changed product should resync"


async def test_an_all_noop_import_enqueues_nothing(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    """Re-applying an unchanged file must not churn the index."""
    rows = [row()]
    first = await upload(client, admin_auth_headers, rows)
    await client.post(
        f"{IMPORTS}/{first.json()['id']}/apply", headers=admin_auth_headers
    )

    second = await upload(client, admin_auth_headers, rows)
    with (
        patch("app.search.tasks.reindex_master_product.delay") as per_product,
        patch("app.search.tasks.reindex_products_by_subcategory.delay") as per_sub,
        patch("app.search.tasks.reindex_products_by_category.delay") as per_cat,
    ):
        await client.post(
            f"{IMPORTS}/{second.json()['id']}/apply", headers=admin_auth_headers
        )
    assert per_product.call_count == 0
    assert per_sub.call_count == 0
    assert per_cat.call_count == 0


async def test_category_rename_reaches_its_products_via_the_hook(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """The product search document embeds `category_name_en`, so a rename has
    to refresh the category's products. `search.hooks` already routes a
    `CategoryTranslation` write to the category fan-out — the importer does not
    need to do anything special."""
    first = await upload(client, admin_auth_headers, [row()])
    await client.post(
        f"{IMPORTS}/{first.json()['id']}/apply", headers=admin_auth_headers
    )

    renamed = await upload(
        client, admin_auth_headers, [row(category_name="Fruits & Veg")]
    )
    with patch("app.search.tasks.reindex_products_by_category.delay") as per_cat:
        await client.post(
            f"{IMPORTS}/{renamed.json()['id']}/apply", headers=admin_auth_headers
        )

    category = (await session.exec(select(Category))).all()[0]
    assert per_cat.call_count == 1
    assert per_cat.call_args_list[0].args == (category.id,)


async def test_subcategory_rename_reaches_its_products_via_the_hook(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    first = await upload(client, admin_auth_headers, [row()])
    await client.post(
        f"{IMPORTS}/{first.json()['id']}/apply", headers=admin_auth_headers
    )

    renamed = await upload(
        client, admin_auth_headers, [row(subcategory_name="Fresh Fruit")]
    )
    with patch("app.search.tasks.reindex_products_by_subcategory.delay") as per_sub:
        await client.post(
            f"{IMPORTS}/{renamed.json()['id']}/apply", headers=admin_auth_headers
        )

    sub = (await session.exec(select(Subcategory))).all()[0]
    assert per_sub.call_count == 1
    assert per_sub.call_args_list[0].args == (sub.id,)


async def test_chunked_apply_enqueues_each_product_once(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """APPLY_CHUNK is 200 and the hook drains per commit, so a 250-row import
    spans two drains — and must still enqueue exactly 250 distinct tasks."""
    rows = [row(product_slug=f"p-{i:04d}") for i in range(250)]
    created = await upload(client, admin_auth_headers, rows)
    with patch("app.search.tasks.reindex_master_product.delay") as per_product:
        applied = await client.post(
            f"{IMPORTS}/{created.json()['id']}/apply", headers=admin_auth_headers
        )
    assert applied.json()["status"] == "applied"

    ids = [call.args[0] for call in per_product.call_args_list]
    assert len(ids) == 250, f"expected one task per product, got {len(ids)}"
    assert len(set(ids)) == 250, "a product was enqueued twice"
