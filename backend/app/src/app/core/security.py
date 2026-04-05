from typing import Any, cast

import firebase_admin
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.db.session import get_db_session
from app.models.base import User, UserRole

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    import os
    cred_path = settings.GOOGLE_APPLICATION_CREDENTIALS
    if cred_path and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {"projectId": settings.FIREBASE_PROJECT_ID})
    else:
        # Fallback for test/CI environments without a key file
        firebase_admin.initialize_app(options={"projectId": settings.FIREBASE_PROJECT_ID})

security = HTTPBearer()

async def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict[str, Any]:
    """Verifies the token from the Authorization header using Firebase Admin."""
    token = credentials.credentials
    try:
        # In a real app testing mode, we might mock this decode function
        decoded_token = auth.verify_id_token(token)
        return cast(dict[str, Any], decoded_token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

async def get_current_user(
    decoded_token: dict[str, Any] = Depends(verify_firebase_token),
    session: AsyncSession = Depends(get_db_session)
) -> User:
    """Retrieves the User from the database based on the verified Firebase UID."""
    firebase_uid = decoded_token.get("uid")
    if not firebase_uid:
        raise HTTPException(status_code=401, detail="Token missing UID payload")

    statement = select(User).where(User.firebase_uid == firebase_uid)
    result = await session.exec(statement)
    user = result.first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    return user

async def get_current_seller(current_user: User = Depends(get_current_user)) -> User:
    """Dependency that ensures the current user has the Seller role."""
    if current_user.role != UserRole.Seller and current_user.role != UserRole.Admin:
         raise HTTPException(
             status_code=status.HTTP_403_FORBIDDEN,
             detail="Not enough privileges. Seller role required."
         )
    return current_user

async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency that ensures the current user has the Admin role."""
    if current_user.role != UserRole.Admin:
         raise HTTPException(
             status_code=status.HTTP_403_FORBIDDEN,
             detail="Not enough privileges. Admin role required."
         )
    return current_user
