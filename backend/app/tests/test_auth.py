from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from app.core.security import verify_firebase_token


# Mock the Firebase token verification to return a predefined token payload
async def mock_verify_firebase_token() -> dict[str, Any]:
    return {
        "uid": "mock_firebase_123",
        "email": "mockeduser@example.com",
        "phone_number": "+1234567890"
    }

# Override the FastAPI dependency
app.dependency_overrides[verify_firebase_token] = mock_verify_firebase_token

@pytest.mark.asyncio
async def test_auth_login_creates_new_user() -> None:
    # 1. Send the login request with a mocked Bearer token
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post("/api/v1/auth/login", headers={"Authorization": "Bearer faked_token"})

    assert response.status_code == 200
    data = response.json()

    assert "id" in data
    assert data["firebase_uid"] == "mock_firebase_123"
    assert data["email"] == "mockeduser@example.com"
    assert data["role"] == "customer"
    assert data["is_active"] is True
