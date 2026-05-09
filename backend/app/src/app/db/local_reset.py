# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from urllib.parse import urlparse

LOCAL_HOSTS = {"localhost", "127.0.0.1"}
CANONICAL_DATABASE_NAME = "khanabazaar"
CANONICAL_DATABASE_PORT = 5432
CANONICAL_REDIS_PORT = 6379


def validate_local_connection_urls(database_url: str, redis_url: str) -> None:
    database_target = urlparse(database_url)
    redis_target = urlparse(redis_url)

    if database_target.hostname not in LOCAL_HOSTS:
        raise ValueError("DATABASE_URL must point to localhost or 127.0.0.1")

    if database_target.port != CANONICAL_DATABASE_PORT:
        raise ValueError("DATABASE_URL must target localhost:5432")

    database_name = database_target.path.lstrip("/")
    if database_name != CANONICAL_DATABASE_NAME:
        raise ValueError("DATABASE_URL must target database 'khanabazaar'")

    if redis_target.hostname not in LOCAL_HOSTS:
        raise ValueError("REDIS_URL must point to localhost or 127.0.0.1")

    if redis_target.port != CANONICAL_REDIS_PORT:
        raise ValueError("REDIS_URL must target localhost:6379")
