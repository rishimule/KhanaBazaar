# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
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


# Pooled engine for the FastAPI request path. Uvicorn runs one persistent event
# loop per process, so pooled asyncpg connections are reused safely on that loop
# (and pool_pre_ping drops conns Cloud SQL closed while idle).
engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs())

# Separate NullPool engine for Celery workers + CLI scripts. These run each unit
# of work in its OWN short-lived asyncio.run() loop (see search/tasks._run_async).
# asyncpg connections are bound to the loop that created them; a pooled
# connection returned to the pool and later reused from a *different* loop cannot
# be cleanly closed once its original loop is gone, orphaning the server-side
# Postgres connection. Under a burst (e.g. a reseed → ~1500 reindex tasks) these
# orphans pile up until Postgres hits max_connections. NullPool opens and closes
# a fresh connection per session within the same loop, so nothing is ever reused
# across loops. (FastAPI keeps the pooled `engine` above.)
worker_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    poolclass=NullPool,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency object for FastAPI endpoints."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


def async_session_factory() -> AsyncSession:
    """Async-session factory for code that doesn't use the FastAPI dep system
    (Celery tasks, CLI commands, bulk reindex). Backed by the NullPool
    `worker_engine` so each session opens+closes its own connection within the
    caller's event loop. Caller is responsible for closing via `async with`.
    """
    return AsyncSession(worker_engine, expire_on_commit=False)
