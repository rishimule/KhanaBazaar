# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Verify retry + DLQ wiring on the per-id reindex tasks.

Celery `task_always_eager` mode does not loop autoretries — `self.retry()`
raises a Retry exception synchronously. So we verify the configuration is
correct (autoretry_for, max_retries) and exercise the DLQ on_failure hook
directly. End-to-end retry behavior is covered in production by the
celery worker, not in this unit test.
"""
from __future__ import annotations

import httpx
import pytest
from meilisearch_python_sdk.errors import MeilisearchApiError

from app.search import dlq
from app.search.tasks import (
    _REINDEX_AUTORETRY,
    _REINDEX_MAX_RETRIES,
    _DLQTask,
    reindex_master_product,
    reindex_store,
)


@pytest.fixture(autouse=True)
def _clear_dlq() -> None:
    dlq._client().delete("search:dlq:product")
    dlq._client().delete("search:dlq:store")
    yield
    dlq._client().delete("search:dlq:product")
    dlq._client().delete("search:dlq:store")


def test_reindex_master_product_is_configured_for_retries() -> None:
    assert reindex_master_product.max_retries == _REINDEX_MAX_RETRIES
    assert reindex_master_product.autoretry_for == _REINDEX_AUTORETRY
    assert reindex_master_product.retry_backoff is True
    assert MeilisearchApiError in _REINDEX_AUTORETRY
    assert httpx.HTTPError in _REINDEX_AUTORETRY


def test_reindex_store_is_configured_for_retries() -> None:
    assert reindex_store.max_retries == _REINDEX_MAX_RETRIES
    assert reindex_store.autoretry_for == _REINDEX_AUTORETRY


def test_dlq_kind_set_on_each_task() -> None:
    assert reindex_master_product._dlq_kind == dlq.DEAD_LETTER_KIND_PRODUCT
    assert reindex_store._dlq_kind == dlq.DEAD_LETTER_KIND_STORE


def test_dlq_task_on_failure_pushes_id_for_product() -> None:
    reindex_master_product.on_failure(
        exc=httpx.ConnectError("boom"),
        task_id="t1",
        args=(42,),
        kwargs={},
        einfo=None,
    )
    drained = dlq.drain(dlq.DEAD_LETTER_KIND_PRODUCT)
    assert drained == [42]


def test_dlq_task_on_failure_pushes_id_for_store() -> None:
    reindex_store.on_failure(
        exc=httpx.ConnectError("boom"),
        task_id="t2",
        args=(77,),
        kwargs={},
        einfo=None,
    )
    drained = dlq.drain(dlq.DEAD_LETTER_KIND_STORE)
    assert drained == [77]


def test_dlq_task_swallows_redis_failures() -> None:
    # If the DLQ push itself fails, on_failure must not escalate — the
    # original exception is already on its way up the Celery stack.
    class Broken(_DLQTask):
        abstract = True
        _dlq_kind = dlq.DEAD_LETTER_KIND_PRODUCT

    broken = Broken()
    # No assertion needed beyond not raising. We pass an arg that can't
    # be int()-ed to force the inner try/except path.
    broken.on_failure(
        exc=httpx.ConnectError("boom"),
        task_id="t3",
        args=("not-an-int",),
        kwargs={},
        einfo=None,
    )


def test_dlq_task_no_op_when_kind_unset() -> None:
    class NoKind(_DLQTask):
        abstract = True

    NoKind().on_failure(
        exc=httpx.ConnectError("boom"),
        task_id="t4",
        args=(1,),
        kwargs={},
        einfo=None,
    )
    assert dlq.size(dlq.DEAD_LETTER_KIND_PRODUCT) == 0
