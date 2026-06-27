# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import enum
from typing import Optional

from sqlmodel import Field, UniqueConstraint

from app.models.base import BaseSchema


class PolicyKind(str, enum.Enum):
    # Member names are lowercase and equal their values so the native PG enum
    # ('terms','privacy') created by metadata matches the hand-written migration.
    terms = "terms"
    privacy = "privacy"


class PolicyDocument(BaseSchema, table=True):
    """An admin-published, versioned policy document. `created_at` (from
    BaseSchema) is the publish timestamp. The current document for a kind is
    the row with the highest version."""

    __table_args__ = (
        UniqueConstraint("kind", "version", name="uq_policydocument_kind_version"),
    )
    kind: PolicyKind = Field(nullable=False)
    version: int = Field(nullable=False)
    body: str = Field(nullable=False)
    # No FK: history survives admin deletion (mirrors admin_action_log).
    published_by: Optional[int] = Field(default=None)


class PolicyAcceptance(BaseSchema, table=True):
    """Append-only record of which effective policy version a user accepted.
    `created_at` (from BaseSchema) is the acceptance timestamp."""

    __table_args__ = (
        UniqueConstraint(
            "user_id", "policy_version", name="uq_policyacceptance_user_version"
        ),
    )
    user_id: int = Field(foreign_key="user.id", index=True, nullable=False)
    policy_version: str = Field(nullable=False)
