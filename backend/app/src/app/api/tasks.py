from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel

from app.worker import test_celery_task

router = APIRouter()

class TaskRequest(BaseModel):
    word: str

@router.post("/test-celery", response_model=Dict[str, Any])
async def trigger_celery_task(request: TaskRequest) -> Any:
    """
    Endpoint to trigger a dummy background task.
    """
    task = test_celery_task.delay(request.word)
    return {
        "message": "Task submitted to Celery",
        "task_id": task.id
    }
