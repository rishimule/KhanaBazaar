# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

# FastAPI engine: long-lived event loop, pooling is a win.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,  # Set to False in production
    future=True,
)

# Celery/CLI engine: these contexts run a fresh event loop per unit of work
# (`asyncio.run` per task in app.search.tasks._run_async). A pooled asyncpg
# connection created on one loop and reused on the next raises
# "another operation is in progress". NullPool opens+closes a fresh connection
# per session, bound to the current loop — no cross-loop reuse.
task_engine = create_async_engine(
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
    (Celery tasks, CLI commands, bulk reindex). Caller is responsible for
    closing the session via `async with`.

    Uses the NullPool ``task_engine`` so each unit of work gets a fresh
    connection bound to its own (per-task) event loop.
    """
    return AsyncSession(task_engine, expire_on_commit=False)
