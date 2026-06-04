# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Guard: the worker/CLI session factory must NOT use a cross-loop connection
pool. Celery search tasks run each unit of work in its own short-lived
asyncio.run() loop (search/tasks._run_async); asyncpg connections are loop-bound,
so a pooled connection reused from a destroyed loop orphans a Postgres
connection. NullPool opens+closes per session within the same loop, preventing
the burst-driven connection leak that exhausts Postgres max_connections.
"""
from sqlalchemy.pool import NullPool

from app.db import session as db_session


def test_worker_engine_uses_nullpool():
    # The worker/CLI engine backing async_session_factory must be NullPool.
    # (The pooled FastAPI request engine is covered by test_db_engine_pool.py;
    # conftest reassigns db_session.engine to a NullPool test engine, so it
    # can't be asserted here.)
    assert isinstance(db_session.worker_engine.pool, NullPool)
