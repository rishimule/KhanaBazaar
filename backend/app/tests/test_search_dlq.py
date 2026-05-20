# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest

from app.search import dlq
from app.search.dlq import (
    DEAD_LETTER_KIND_PRODUCT,
    DEAD_LETTER_KIND_STORE,
    drain,
    push,
    size,
)


@pytest.fixture(autouse=True)
def _clear() -> None:
    dlq._client().delete(f"search:dlq:{DEAD_LETTER_KIND_PRODUCT}")
    dlq._client().delete(f"search:dlq:{DEAD_LETTER_KIND_STORE}")
    yield
    dlq._client().delete(f"search:dlq:{DEAD_LETTER_KIND_PRODUCT}")
    dlq._client().delete(f"search:dlq:{DEAD_LETTER_KIND_STORE}")


def test_push_and_drain_round_trip() -> None:
    push(DEAD_LETTER_KIND_PRODUCT, 11)
    push(DEAD_LETTER_KIND_PRODUCT, 12)
    push(DEAD_LETTER_KIND_PRODUCT, 11)
    assert size(DEAD_LETTER_KIND_PRODUCT) == 2
    drained = drain(DEAD_LETTER_KIND_PRODUCT)
    assert drained == [11, 12]
    assert size(DEAD_LETTER_KIND_PRODUCT) == 0


def test_drain_when_empty_returns_empty_list() -> None:
    assert drain(DEAD_LETTER_KIND_PRODUCT) == []


def test_kinds_are_isolated() -> None:
    push(DEAD_LETTER_KIND_PRODUCT, 1)
    push(DEAD_LETTER_KIND_STORE, 2)
    assert size(DEAD_LETTER_KIND_PRODUCT) == 1
    assert size(DEAD_LETTER_KIND_STORE) == 1
    assert drain(DEAD_LETTER_KIND_PRODUCT) == [1]
    assert size(DEAD_LETTER_KIND_PRODUCT) == 0
    assert size(DEAD_LETTER_KIND_STORE) == 1
