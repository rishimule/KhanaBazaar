# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Staged CSV catalog imports.

Two tables back the two-phase admin bulk import:

* :class:`CatalogImportJob` — one row per uploaded file. Holds the status, the
  planned per-level create/update counts, and (after apply) what actually
  landed. This row is also the **audit record** for the import: catalog writes
  cannot use ``admin_action_log`` because its ``target_seller_id`` is a NOT NULL
  FK to ``sellerprofile`` and the catalog is not seller-scoped.

* :class:`CatalogImportRow` — one row per CSV data line, carrying the normalized
  cell values, the per-level verdicts, and any validation errors. Staging every
  line is what makes "preview" a guarantee rather than a hint: apply writes
  exactly these rows, and the error report paginates server-side instead of
  being shipped to the browser as one blob.

Enums use ``values_callable`` so the native PG enum stores the lowercase VALUES
(mirrors ``notification_campaign.py``).
"""
import enum
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import Column, DateTime, Index
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseSchema


class CatalogImportStatus(str, enum.Enum):
    """Lifecycle of an uploaded file.

    ``Validated`` means parsed + staged with nothing written to the catalog —
    every upload lands here. ``Failed`` is re-appliable: apply skips rows that
    already carry ``applied_at``, so a worker death mid-import resumes.
    """

    Validated = "validated"
    Applying = "applying"
    Applied = "applied"
    Failed = "failed"
    Cancelled = "cancelled"


class CatalogImportRowAction(str, enum.Enum):
    """Validation verdict for one CSV line.

    ``Noop`` means every level already matches the live catalog — which is what
    a freshly exported, unedited file produces end to end.
    """

    Create = "create"
    Update = "update"
    Noop = "noop"
    Error = "error"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Serialize enum members by VALUE (lowercase PG labels)."""
    return [m.value for m in enum_cls]


class CatalogImportJob(BaseSchema, table=True):
    __tablename__ = "catalog_import_job"

    filename: str = Field(max_length=255, nullable=False)
    status: CatalogImportStatus = Field(
        default=CatalogImportStatus.Validated,
        sa_column=Column(
            SAEnum(
                CatalogImportStatus,
                name="catalogimportstatus",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=False,
            index=True,
        ),
    )
    created_by_admin_id: int = Field(foreign_key="user.id", nullable=False, index=True)
    total_rows: int = Field(default=0, nullable=False)
    error_rows: int = Field(default=0, nullable=False)
    # plan / applied: {"service": {"create": n, "update": n}, "category": {...},
    # "subcategory": {...}, "product": {...}}. `plan` is what the preview
    # promised; `applied` is what the apply pass actually wrote.
    plan: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    applied: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    failure_reason: Optional[str] = Field(default=None, max_length=500)
    applied_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )


class CatalogImportRow(BaseSchema, table=True):
    __tablename__ = "catalog_import_row"
    __table_args__ = (
        Index("ix_catalog_import_row_job_line", "job_id", "line_number"),
        Index("ix_catalog_import_row_job_action", "job_id", "action"),
    )

    job_id: int = Field(foreign_key="catalog_import_job.id", nullable=False)
    # 1-based index into the CSV's DATA lines (header excluded), so it matches
    # what a spreadsheet shows once you account for the header row.
    line_number: int = Field(nullable=False)
    action: CatalogImportRowAction = Field(
        sa_column=Column(
            SAEnum(
                CatalogImportRowAction,
                name="catalogimportrowaction",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=False,
        )
    )
    # Normalized cell values keyed by CSV column name. Blank optional cells are
    # dropped rather than stored as "", so apply can distinguish "leave alone"
    # from "set to empty".
    data: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    # [{"column": "base_price", "code": "price_invalid", "message": "..."}]
    errors: List[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )
    # {"service": "noop", "category": "create", "subcategory": "noop",
    #  "product": "update"} — per-level verdict, so the preview can say which
    # parents a row would bring into existence.
    level_plan: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    applied_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    apply_error: Optional[str] = Field(default=None, max_length=500)
