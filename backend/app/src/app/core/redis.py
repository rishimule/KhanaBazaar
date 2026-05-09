# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from functools import lru_cache

import redis.asyncio as aioredis

from app.core.config import settings


@lru_cache(maxsize=1)
def _make_redis() -> aioredis.Redis:
    return aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_redis() -> aioredis.Redis:
    return _make_redis()
