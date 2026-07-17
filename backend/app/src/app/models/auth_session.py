# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, String, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import DateTime, Field

from app.models.base import BaseSchema


class AuthSession(BaseSchema, table=True):
    """A server-side refresh session backing long-term sign-in.

    One row per login. ``refresh_token_hash`` is the SHA-256 hex of the current
    (rotated) refresh token — the raw token is never stored. ``created_at`` (from
    ``BaseSchema``) is the issue time; ``last_used_at`` drives the sliding idle
    timeout; ``absolute_expires_at`` is the hard ceiling.
    """

    user_id: int = Field(foreign_key="user.id", index=True, nullable=False)
    refresh_token_hash: str = Field(index=True, nullable=False)
    prev_token_hash: Optional[str] = Field(default=None, index=True)
    prev_rotated_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    trusted: bool = Field(default=False, nullable=False)
    last_used_at: datetime = Field(  # type: ignore[call-overload]
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    absolute_expires_at: datetime = Field(  # type: ignore[call-overload]
        sa_type=DateTime(timezone=True), nullable=False
    )
    revoked_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    device_label: str = Field(default="", nullable=False)
    user_agent: str = Field(default="", nullable=False)
    ip: Optional[str] = Field(default=None)
    rotated_hashes: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default=text("'{}'")),
    )
