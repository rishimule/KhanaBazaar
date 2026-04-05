import time

from typing import Any

from app.core.celery_app import celery_app

@celery_app.task(name="test_celery_task", bind=True)  # type: ignore
def test_celery_task(self: Any, word: str) -> str:
    """
    A simple dummy task to test the Celery queue.
    Simulates a long-running process like sending an email.
    """
    time.sleep(2)  # Simulate blocking work
    return f"Celery processed the word: {word}"
