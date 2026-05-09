# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
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
