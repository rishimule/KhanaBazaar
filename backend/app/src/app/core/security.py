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


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_db_session),
) -> User | None:
    """Like get_current_user but never raises: returns None when no/invalid
    bearer token is present. For public endpoints that want to *attribute* a
    submission to a logged-in user without requiring auth."""
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except HTTPException:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    try:
        uid = int(str(user_id))
    except (ValueError, TypeError):
        return None
    result = await session.exec(select(User).where(User.id == uid))
    user = result.first()
    if not user or not user.is_active:
        return None
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


def create_referral_invite_token(
    *,
    referral_id: int,
    target_role: str,
    email: str | None,
    phone: str | None,
    expires_days: int,
) -> str:
    """Mint an invite JWT binding a referral to the invitee's contact.

    This is the passwordless equivalent of the spec's "temporary credentials":
    it carries no secret the user must set, only a signed, expiring claim that
    the bearer was invited to onboard as ``target_role``.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(referral_id),
        "target_role": target_role,
        "email": email,
        "phone": phone,
        "type": "referral_invite",
        "iat": now,
        "exp": now + timedelta(days=expires_days),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_referral_invite_token(token: str) -> dict[str, object]:
    """Validate an invite token. Returns claims dict; raises 410/400 on failure."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"error": "invite_token_expired"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_invite_token"},
        ) from None
    if payload.get("type") != "referral_invite":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_invite_token"},
        )
    return {
        "referral_id": int(str(payload["sub"])),
        "target_role": str(payload["target_role"]),
        "email": payload.get("email"),
        "phone": payload.get("phone"),
    }


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
    sub = payload.get("sub")
    phone = payload.get("phone")
    if (
        payload.get("type") != "seller_phone_change"
        or sub is None
        or phone is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_phone_change_token"},
        )
    try:
        return int(sub), str(phone)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_phone_change_token"},
        ) from None
