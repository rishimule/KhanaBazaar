import redis.asyncio as aioredis


async def incr_with_ttl(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    key: str,
    ttl: int,
) -> int:
    """Increment counter at key; set TTL only on first increment so the window doesn't reset."""
    count: int = await redis.incr(key)
    if count == 1:
        await redis.expire(key, ttl)
    return count


async def seconds_until(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    key: str,
) -> int:
    """Return seconds until key expires. -1 = no TTL, -2 = key does not exist."""
    result: int = await redis.ttl(key)
    return result
