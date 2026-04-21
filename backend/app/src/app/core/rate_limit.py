import redis.asyncio as aioredis


async def incr_with_ttl(
    redis: aioredis.Redis,
    key: str,
    ttl: int,
) -> int:
    count: int = await redis.incr(key)
    if count == 1:
        await redis.expire(key, ttl)
    return count


async def seconds_until(
    redis: aioredis.Redis,
    key: str,
) -> int:
    result: int = await redis.ttl(key)
    return result
