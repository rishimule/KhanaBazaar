# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Redis-backed dead-letter queues for Meilisearch sync tasks.

Push an id on terminal failure. The reconciler drains and re-enqueues
the ids at its next pass so a transient outage cannot quietly orphan
the index from the source of truth.
"""
from __future__ import annotations

from typing import Literal

import redis

from app.core.config import settings

DeadLetterKind = Literal["product", "store"]
DEAD_LETTER_KIND_PRODUCT: DeadLetterKind = "product"
DEAD_LETTER_KIND_STORE: DeadLetterKind = "store"

_client_singleton: redis.Redis | None = None


def _client() -> redis.Redis:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = redis.Redis.from_url(settings.REDIS_URL)
    return _client_singleton


def _key(kind: DeadLetterKind) -> str:
    return f"search:dlq:{kind}"


def push(kind: DeadLetterKind, id_: int) -> None:
    _client().sadd(_key(kind), id_)


def drain(kind: DeadLetterKind) -> list[int]:
    pipe = _client().pipeline()
    pipe.smembers(_key(kind))
    pipe.delete(_key(kind))
    members, _ = pipe.execute()
    return sorted(int(m) for m in members)


def size(kind: DeadLetterKind) -> int:
    return int(_client().scard(_key(kind)))  # type: ignore[arg-type]
