from urllib.parse import urlparse


LOCAL_HOSTS = {"localhost", "127.0.0.1"}
CANONICAL_DATABASE_NAME = "khanabazaar"


def validate_local_connection_urls(database_url: str, redis_url: str) -> None:
    database_target = urlparse(database_url)
    redis_target = urlparse(redis_url)

    if database_target.hostname not in LOCAL_HOSTS:
        raise ValueError("DATABASE_URL must point to localhost or 127.0.0.1")

    database_name = database_target.path.lstrip("/")
    if database_name != CANONICAL_DATABASE_NAME:
        raise ValueError("DATABASE_URL must target database 'khanabazaar'")

    if redis_target.hostname not in LOCAL_HOSTS:
        raise ValueError("REDIS_URL must point to localhost or 127.0.0.1")
