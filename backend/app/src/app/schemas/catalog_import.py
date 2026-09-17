# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Request + response schemas for admin bulk catalog operations.

Covers the two-phase CSV import (`/catalog/admin/imports/*`) and the in-grid
multi-select activation toggle (`/catalog/admin/bulk/status`).
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# Mirrors `EntityKind` on the frontend and the four admin CRUD groups.
BulkEntity = Literal["service", "category", "subcategory", "product"]


class LevelCounts(BaseModel):
    create: int = 0
    update: int = 0
    noop: int = 0


class ImportPlan(BaseModel):
    """Per-level counts of DISTINCT paths, not rows.

    Every row under one new category reports `category: create`, but the
    category is created once — so these numbers answer "what will change",
    not "how many lines mention it".
    """

    service: LevelCounts = Field(default_factory=LevelCounts)
    category: LevelCounts = Field(default_factory=LevelCounts)
    subcategory: LevelCounts = Field(default_factory=LevelCounts)
    product: LevelCounts = Field(default_factory=LevelCounts)


class ImportJobRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    filename: str
    status: str
    created_by_admin_id: int
    total_rows: int
    error_rows: int
    plan: ImportPlan = Field(default_factory=ImportPlan)
    applied: Optional[ImportPlan] = None
    failure_reason: Optional[str] = None
    applied_at: Optional[datetime] = None


class ImportRowError(BaseModel):
    column: str
    code: str
    message: str


class ImportRowRead(BaseModel):
    id: int
    line_number: int
    action: str
    # Normalized cells only — blank optional columns are absent rather than "".
    data: Dict[str, Any] = Field(default_factory=dict)
    errors: List[ImportRowError] = Field(default_factory=list)
    level_plan: Dict[str, str] = Field(default_factory=dict)
    applied_at: Optional[datetime] = None
    apply_error: Optional[str] = None


class BulkStatusRequest(BaseModel):
    """Activate or deactivate a selection from the admin catalog table.

    Deliberately narrow: the only field it writes is `is_active`. Bulk field
    editing goes through the CSV round trip, where it is previewable.
    """

    entity: BulkEntity
    ids: List[int] = Field(default_factory=list)
    is_active: bool


class BulkStatusResponse(BaseModel):
    updated: int
    # Ids that were already in the requested state — reported rather than
    # silently counted, so "12 selected, 9 updated" is explainable.
    unchanged: List[int] = Field(default_factory=list)
    not_found: List[int] = Field(default_factory=list)
