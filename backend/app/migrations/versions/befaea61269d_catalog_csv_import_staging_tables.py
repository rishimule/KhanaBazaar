# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""catalog csv import staging tables

Revision ID: befaea61269d
Revises: d4ea73769f60
Create Date: 2026-09-16 19:11:02.114495

Two-phase admin bulk catalog import. `catalog_import_job` is one row per
uploaded file (and doubles as the audit record, since `admin_action_log`
requires a seller target the catalog does not have); `catalog_import_row` is
one row per CSV data line, staged at upload so the apply pass writes exactly
what the preview promised.

Both enums store lowercase VALUES (`values_callable` in the model), matching
`campaignstatus`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'befaea61269d'
down_revision: Union[str, Sequence[str], None] = 'd4ea73769f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    job_status = postgresql.ENUM(
        "validated",
        "applying",
        "applied",
        "failed",
        "cancelled",
        name="catalogimportstatus",
    )
    row_action = postgresql.ENUM(
        "create", "update", "noop", "error", name="catalogimportrowaction"
    )
    job_status.create(op.get_bind(), checkfirst=True)
    row_action.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "catalog_import_job",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="catalogimportstatus", create_type=False),
            nullable=False,
            server_default="validated",
        ),
        sa.Column(
            "created_by_admin_id",
            sa.Integer,
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column("total_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("plan", postgresql.JSONB, nullable=False),
        sa.Column("applied", postgresql.JSONB, nullable=False),
        sa.Column("failure_reason", sa.String(length=500)),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_catalog_import_job_status", "catalog_import_job", ["status"]
    )
    op.create_index(
        "ix_catalog_import_job_created_by_admin_id",
        "catalog_import_job",
        ["created_by_admin_id"],
    )

    op.create_table(
        "catalog_import_row",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "job_id",
            sa.Integer,
            sa.ForeignKey("catalog_import_job.id"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column(
            "action",
            postgresql.ENUM(name="catalogimportrowaction", create_type=False),
            nullable=False,
        ),
        sa.Column("data", postgresql.JSONB, nullable=False),
        sa.Column("errors", postgresql.JSONB, nullable=False),
        sa.Column("level_plan", postgresql.JSONB, nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("apply_error", sa.String(length=500)),
    )
    op.create_index(
        "ix_catalog_import_row_job_line",
        "catalog_import_row",
        ["job_id", "line_number"],
    )
    op.create_index(
        "ix_catalog_import_row_job_action",
        "catalog_import_row",
        ["job_id", "action"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_catalog_import_row_job_action", table_name="catalog_import_row"
    )
    op.drop_index(
        "ix_catalog_import_row_job_line", table_name="catalog_import_row"
    )
    op.drop_table("catalog_import_row")
    op.drop_index(
        "ix_catalog_import_job_created_by_admin_id",
        table_name="catalog_import_job",
    )
    op.drop_index("ix_catalog_import_job_status", table_name="catalog_import_job")
    op.drop_table("catalog_import_job")
    op.execute("DROP TYPE IF EXISTS catalogimportrowaction")
    op.execute("DROP TYPE IF EXISTS catalogimportstatus")
