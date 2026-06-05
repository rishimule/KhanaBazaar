# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import asyncio

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

from app.core.config import settings

celery_app = Celery(
    "khanabazaar",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)


@worker_process_init.connect
def _dispose_inherited_db_engine(**_kwargs: object) -> None:
    """Reset the shared async DB engine after a prefork worker forks.

    The module-level `engine` in `app.db.session` is created in the parent
    process. Forked children inherit its pooled asyncpg connections; two
    children using the same inherited socket raises asyncpg's
    "another operation is in progress". Dispose with ``close=False`` so the
    child abandons (without closing) the inherited connections and lazily
    opens its own — the documented SQLAlchemy fork-safety pattern.
    """
    from app.db.session import engine

    asyncio.run(engine.dispose(close=False))

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)

# Optional: Load task modules here so Celery can discover them
# celery_app.autodiscover_tasks(["app.worker"])

celery_app.conf.beat_schedule = {
    "search-rebuild-terms-nightly": {
        "task": "search.rebuild_search_terms",
        "schedule": crontab(hour=3, minute=15),
    },
    "search-prune-query-log-daily": {
        "task": "search.prune_query_log",
        "schedule": crontab(hour=4, minute=0),
    },
    # verify_drift is kept wired for one transition release while the new
    # reconciler proves itself. Remove once 7 days of clean reconcile runs
    # accumulate (see specs/2026-05-20-search-index-production-design.md).
    "search-verify-drift-nightly": {
        "task": "search.verify_drift",
        "schedule": crontab(hour=4, minute=30),
    },
    "search-reconcile-products-hourly": {
        "task": "search.reconcile_index",
        "schedule": crontab(minute=7),
        "args": ("product", False),
    },
    "search-reconcile-products-daily-deep": {
        "task": "search.reconcile_index",
        "schedule": crontab(hour=4, minute=30),
        "args": ("product", True),
    },
    "search-reconcile-stores-hourly": {
        "task": "search.reconcile_index",
        "schedule": crontab(minute=22),
        "args": ("store", False),
    },
    "search-reconcile-stores-daily-deep": {
        "task": "search.reconcile_index",
        "schedule": crontab(hour=4, minute=45),
        "args": ("store", True),
    },
}
