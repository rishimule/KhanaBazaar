import pytest

from app.db.local_reset import validate_local_connection_urls


def test_validate_local_connection_urls_accepts_canonical_local_targets() -> None:
    validate_local_connection_urls(
        "postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar",
        "redis://127.0.0.1:6379/0",
    )


@pytest.mark.parametrize(
    ("database_url", "redis_url", "message"),
    [
        (
            "postgresql+asyncpg://postgres:password@db.internal:5432/khanabazaar",
            "redis://127.0.0.1:6379/0",
            "DATABASE_URL must point to localhost or 127.0.0.1",
        ),
        (
            "postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar_staging",
            "redis://127.0.0.1:6379/0",
            "DATABASE_URL must target database 'khanabazaar'",
        ),
        (
            "postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar",
            "redis://cache.internal:6379/0",
            "REDIS_URL must point to localhost or 127.0.0.1",
        ),
        (
            "postgresql+asyncpg://postgres:password@localhost:15432/khanabazaar",
            "redis://127.0.0.1:6379/0",
            "DATABASE_URL must target localhost:5432",
        ),
        (
            "postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar",
            "redis://127.0.0.1:16379/0",
            "REDIS_URL must target localhost:6379",
        ),
    ],
)
def test_validate_local_connection_urls_rejects_non_local_targets(
    database_url: str,
    redis_url: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_local_connection_urls(database_url, redis_url)
