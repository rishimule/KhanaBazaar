# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Unit tests for the reconciler diff core. Orchestration tests live in
test_search_reconcile_integration.py once Task 5 lands.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.search import dlq
from app.search.reconcile import (
    ABORT_KEY_TEMPLATE,
    COMPARE_FIELDS_PRODUCT,
    SHARDS,
    ShardDeltas,
    _redis_client,
    current_shard,
    diff_shard,
    read_summary,
    reconcile_products,
    reconcile_stores,
    total_deltas,
)
from app.search.reindex import reindex_products, reindex_stores


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


# ─── Integration: real Postgres + real Meili ────────────────────────────────


async def _seed_minimal_product(session: AsyncSession) -> int:
    """Insert one master product + supporting graph. Return its id."""
    from app.models.address import Address
    from app.models.base import User, UserRole
    from app.models.catalog import (
        Category,
        CategoryTranslation,
        MasterProduct,
        MasterProductTranslation,
        Service,
        ServiceTranslation,
        Subcategory,
        SubcategoryTranslation,
    )
    from app.models.profile import SellerProfile, VerificationStatus
    from app.models.store import Store, StoreInventory
    from tests._helpers import make_address

    user = User(email="rec-test@kb.com", role=UserRole.Seller, is_active=True)
    session.add(user)
    await session.flush()
    biz = Address(**make_address(pincode="400001"))
    session.add(biz)
    await session.flush()
    seller = SellerProfile(
        user_id=user.id, first_name="R", phone="+919900000001",
        business_name="X", bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz.id,
    )
    session.add(seller)
    await session.flush()
    store_addr = Address(**make_address(latitude=19.07, longitude=72.87, pincode="400002"))
    session.add(store_addr)
    await session.flush()
    store = Store(
        name="Rec Test Store", seller_profile_id=seller.id, address_id=store_addr.id,
        is_active=True, delivery_radius_km=5,
    )
    session.add(store)
    await session.flush()
    svc = Service(slug="rec-grocery", is_active=True)
    session.add(svc)
    await session.flush()
    session.add(ServiceTranslation(service_id=svc.id, language_code="en", name="Grocery"))
    cat = Category(service_id=svc.id, slug="rec-dairy", is_active=True)
    session.add(cat)
    await session.flush()
    session.add(CategoryTranslation(category_id=cat.id, language_code="en", name="Dairy"))
    sub = Subcategory(category_id=cat.id, slug="rec-milk", is_active=True)
    session.add(sub)
    await session.flush()
    session.add(SubcategoryTranslation(subcategory_id=sub.id, language_code="en", name="Milk"))
    product = MasterProduct(
        subcategory_id=sub.id, slug="rec-amul", base_price=50.0,
        brand="Amul", unit="1L", is_active=True,
    )
    session.add(product)
    await session.flush()
    session.add(MasterProductTranslation(
        master_product_id=product.id, language_code="en",
        name="Rec Amul Gold", description="x",
    ))
    session.add(StoreInventory(
        store_id=store.id, product_id=product.id,
        price=48.0, stock=10, is_available=True,
    ))
    pid = product.id
    await session.commit()
    return pid


def _clear_reconcile_state(kind: str) -> None:
    r = _redis_client()
    r.delete(f"search:reconcile:last:{kind}")
    r.delete(ABORT_KEY_TEMPLATE.format(kind=kind))
    r.delete(f"search:dlq:{kind}")


@pytest.mark.asyncio
async def test_reconcile_products_cheap_clean_when_in_sync(
    session: AsyncSession, meili_test_client
) -> None:
    _clear_reconcile_state("product")
    pid = await _seed_minimal_product(session)
    await reindex_products(session, meili_test_client)

    summary = await reconcile_products(session, meili_test_client)
    assert summary.mode == "cheap_clean"
    assert summary.deltas.missing == []
    assert summary.deltas.modified == []
    assert summary.deltas.extra == []
    assert pid > 0


@pytest.mark.asyncio
async def test_reconcile_products_detects_missing_meili_doc(
    session: AsyncSession, meili_test_client
) -> None:
    _clear_reconcile_state("product")
    pid = await _seed_minimal_product(session)
    await reindex_products(session, meili_test_client)

    products_index = meili_test_client.index("products")
    delete_task = await products_index.delete_document(pid)
    await meili_test_client.wait_for_task(delete_task.task_uid)

    # Pin current_shard so the deep pass walks the shard our product lives in.
    target_shard = pid % SHARDS
    with patch(
        "app.search.reconcile.current_shard",
        return_value=target_shard,
    ):
        with patch(
            "app.search.tasks.reindex_master_product.delay",
            lambda *a, **kw: None,
        ):
            summary = await reconcile_products(
                session, meili_test_client, force_deep=True
            )

    assert summary.mode == "deep"
    assert pid in summary.deltas.missing


@pytest.mark.asyncio
async def test_reconcile_products_detects_meili_extra(
    session: AsyncSession, meili_test_client
) -> None:
    _clear_reconcile_state("product")
    pid = await _seed_minimal_product(session)
    await reindex_products(session, meili_test_client)

    # Inject an orphan doc into Meili — no matching DB row.
    products_index = meili_test_client.index("products")
    orphan_id = 9_000_001  # high id, very unlikely to collide
    task = await products_index.add_documents(
        [{"id": orphan_id, "name_en": "ghost", "db_updated_at": 1}], primary_key="id"
    )
    await meili_test_client.wait_for_task(task.task_uid)

    target_shard = orphan_id % SHARDS
    with patch(
        "app.search.reconcile.current_shard",
        return_value=target_shard,
    ):
        with patch(
            "app.search.tasks.reindex_master_product.delay",
            lambda *a, **kw: None,
        ):
            summary = await reconcile_products(
                session, meili_test_client, force_deep=True
            )

    assert orphan_id in summary.deltas.extra
    assert pid > 0


@pytest.mark.asyncio
async def test_reconcile_writes_summary_to_redis(
    session: AsyncSession, meili_test_client
) -> None:
    _clear_reconcile_state("product")
    pid = await _seed_minimal_product(session)
    await reindex_products(session, meili_test_client)

    await reconcile_products(session, meili_test_client)
    stored = read_summary(_redis_client(), "product")
    assert stored is not None
    assert stored["kind"] == "product"
    assert stored["mode"] == "cheap_clean"
    assert pid > 0


@pytest.mark.asyncio
async def test_reconcile_drains_dlq_at_start(
    session: AsyncSession, meili_test_client
) -> None:
    _clear_reconcile_state("product")
    _ = await _seed_minimal_product(session)
    await reindex_products(session, meili_test_client)

    dlq.push("product", 12345)
    dlq.push("product", 67890)

    enqueued: list[int] = []

    def fake_delay(id_: int) -> None:
        enqueued.append(id_)

    with patch(
        "app.search.tasks.reindex_master_product.delay",
        side_effect=fake_delay,
    ):
        summary = await reconcile_products(session, meili_test_client)

    assert summary.dlq_drained == 2
    assert sorted(enqueued)[:2] == [12345, 67890]
    assert dlq.size("product") == 0


@pytest.mark.asyncio
async def test_reconcile_respects_abort_flag(
    session: AsyncSession, meili_test_client
) -> None:
    _clear_reconcile_state("product")
    r = _redis_client()
    r.set(ABORT_KEY_TEMPLATE.format(kind="product"), "1", ex=86400)

    summary = await reconcile_products(session, meili_test_client)
    assert summary.mode == "aborted_held"
    assert summary.error == "abort flag set"

    r.delete(ABORT_KEY_TEMPLATE.format(kind="product"))


@pytest.mark.asyncio
async def test_reconcile_stores_smoke(
    session: AsyncSession, meili_test_client
) -> None:
    _clear_reconcile_state("store")
    await _seed_minimal_product(session)
    await reindex_stores(session, meili_test_client)
    summary = await reconcile_stores(session, meili_test_client)
    assert summary.mode == "cheap_clean"


def test_reconcile_index_task_routes_to_correct_kind() -> None:
    from unittest.mock import AsyncMock

    from app.search.tasks import reconcile_index

    with patch("app.search.reconcile.reconcile_products", new_callable=AsyncMock) as p, \
         patch("app.search.reconcile.reconcile_stores", new_callable=AsyncMock) as s:
        reconcile_index.apply(args=["product", False]).get(disable_sync_subtasks=False)
        reconcile_index.apply(args=["store", True]).get(disable_sync_subtasks=False)

    assert p.await_count == 1
    assert s.await_count == 1
    # force_deep flag propagates.
    assert s.await_args.kwargs == {"force_deep": True}
    assert p.await_args.kwargs == {"force_deep": False}


def test_reconcile_index_task_raises_on_unknown_kind() -> None:
    from app.search.tasks import reconcile_index

    with pytest.raises(ValueError, match="unknown reconcile kind"):
        reconcile_index.apply(args=["bogus", False]).get(disable_sync_subtasks=False)


def test_beat_schedule_includes_reconcile_jobs() -> None:
    from app.core.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "search-reconcile-products-hourly" in schedule
    assert "search-reconcile-products-daily-deep" in schedule
    assert "search-reconcile-stores-hourly" in schedule
    assert "search-reconcile-stores-daily-deep" in schedule
    assert schedule["search-reconcile-products-hourly"]["args"] == ("product", False)
    assert schedule["search-reconcile-products-daily-deep"]["args"] == ("product", True)
