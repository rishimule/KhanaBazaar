# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "khanabazaar",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

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
    "search-verify-drift-nightly": {
        "task": "search.verify_drift",
        "schedule": crontab(hour=4, minute=30),
    },
}
