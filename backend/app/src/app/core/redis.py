from functools import lru_cache

import redis.asyncio as aioredis

from app.core.config import settings


@lru_cache(maxsize=1)
def _make_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    return aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    return _make_redis()
