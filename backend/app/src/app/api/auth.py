from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import verify_firebase_token
from app.db.session import get_db_session
from app.models.base import User, UserRole

router = APIRouter()

@router.post("/login", response_model=User)
async def login_for_access_token(
    decoded_token: dict[str, Any] = Depends(verify_firebase_token),
    session: AsyncSession = Depends(get_db_session)
) -> User:
    """
    Login endpoint that verifies a Firebase token, retrieves the associated
    user from the database, or creates a new Customer user if they do not exist.
    """
    firebase_uid = decoded_token.get("uid")
    email = decoded_token.get("email")

    # Try to find the existing user
    statement = select(User).where(User.firebase_uid == firebase_uid)
    result = await session.exec(statement)
    user = result.first()

    if not user:
        # User doesn't exist, create a new customer stub
        new_user = User(
            firebase_uid=firebase_uid,
            email=email,  # May be null if using OTP
            role=UserRole.Customer,
            is_active=True
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        return new_user

    return user
