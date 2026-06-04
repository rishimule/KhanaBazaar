# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings


def _engine_kwargs() -> dict:  # type: ignore[type-arg]
    """Engine settings tuned for Cloud SQL db-f1-micro (~26 max connections).

    Each Cloud Run instance keeps a small pool so several instances + the
    Celery worker don't exhaust the DB. pool_pre_ping drops stale conns that
    Cloud SQL closed during idle scale-to-zero windows.
    """
    return {
        "echo": settings.ENVIRONMENT != "production",
        "future": True,
        "pool_size": 2,
        "max_overflow": 3,
        "pool_pre_ping": True,
    }


engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs())

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency object for FastAPI endpoints."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


def async_session_factory() -> AsyncSession:
    """Async-session factory for code that doesn't use the FastAPI dep system
    (Celery tasks, CLI commands, bulk reindex). Caller is responsible for
    closing the session via `async with`.
    """
    return AsyncSession(engine, expire_on_commit=False)
