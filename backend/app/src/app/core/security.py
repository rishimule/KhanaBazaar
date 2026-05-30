# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.db.session import get_db_session
from app.models.base import User, UserRole

security = HTTPBearer(auto_error=False)


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRES_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, object]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def verify_access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, object]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)


async def get_current_user(
    payload: dict[str, object] = Depends(verify_access_token),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing sub claim")

    statement = select(User).where(User.id == int(str(user_id)))
    result = await session.exec(statement)
    user = result.first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    return user


async def get_current_customer(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.Customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges. Customer role required.",
        )
    return current_user


async def get_current_seller(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.Seller, UserRole.Admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges. Seller role required.",
        )
    return current_user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.Admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges. Admin role required.",
        )
    return current_user


def create_seller_email_token(email: str) -> str:
    """Mint a 10-minute JWT proving the seller has verified their email."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "type": "seller_email",
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_seller_email_token(token: str) -> str:
    """Validate the seller email-stage token. Returns email on success."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"error": "email_token_expired"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_email_token"},
        ) from None
    if payload.get("type") != "seller_email":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_email_token"},
        )
    return str(payload["sub"])


def create_seller_signup_token(email: str, phone: str) -> str:
    """Mint a 10-minute JWT proving the seller verified both email and phone."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "phone": phone,
        "type": "seller_signup",
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_seller_signup_token(token: str) -> tuple[str, str]:
    """Validate the seller signup token. Returns (email, phone)."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"error": "signup_token_expired"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_signup_token"},
        ) from None
    if payload.get("type") != "seller_signup":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_signup_token"},
        )
    return str(payload["sub"]), str(payload["phone"])


def create_seller_phone_change_token(user_id: int, phone: str) -> str:
    """Mint a 10-minute JWT proving the seller verified control of `phone`."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "phone": phone,
        "type": "seller_phone_change",
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_seller_phone_change_token(token: str) -> tuple[int, str]:
    """Validate a phone-change token. Returns (user_id, phone)."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"error": "phone_change_token_expired"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_phone_change_token"},
        ) from None
    if payload.get("type") != "seller_phone_change":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_phone_change_token"},
        )
    return int(payload["sub"]), str(payload["phone"])
