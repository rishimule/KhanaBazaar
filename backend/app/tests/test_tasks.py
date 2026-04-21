import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from app.core.celery_app import celery_app

# Put Celery into eager mode for testing so tasks execute synchronously within the same process
celery_app.conf.update(task_always_eager=True)

@pytest.mark.asyncio
async def test_trigger_celery_task() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        req_data = {"word": "KhanaBazaarBackground"}
        response = await ac.post("/api/v1/tasks/test-celery", json=req_data)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Task submitted to Celery"
        assert "task_id" in data
