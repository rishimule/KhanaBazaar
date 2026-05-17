# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Helpers for writing admin-action audit rows.

The :func:`log` helper adds an :class:`AdminActionLog` row to the *open*
session without committing. The caller is responsible for the surrounding
transaction so the audit row stays atomic with the mutation it documents:
if the mutation rolls back, the audit row does too.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.admin_audit import AdminActionLog, AdminActionTargetType


async def log(
    *,
    session: AsyncSession,
    admin_user_id: int,
    target_seller_id: int,
    target_type: AdminActionTargetType,
    target_id: int,
    action: str,
    before_json: Optional[dict[str, Any]] = None,
    after_json: Optional[dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> AdminActionLog:
    row = AdminActionLog(
        admin_user_id=admin_user_id,
        target_seller_id=target_seller_id,
        target_type=target_type,
        target_id=target_id,
        action=action,
        before_json=before_json,
        after_json=after_json,
        reason=reason,
    )
    session.add(row)
    return row
