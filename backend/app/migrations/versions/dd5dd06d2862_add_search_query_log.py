# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add search_query_log

Revision ID: dd5dd06d2862
Revises: d3f0983b94eb
Create Date: 2026-05-15 20:58:05.089476

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dd5dd06d2862"
down_revision: Union[str, Sequence[str], None] = "d3f0983b94eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_query_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("query_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "session_id",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
        sa.Column(
            "query",
            sqlmodel.sql.sqltypes.AutoString(length=100),
            nullable=False,
        ),
        sa.Column(
            "locale",
            sqlmodel.sql.sqltypes.AutoString(length=8),
            nullable=False,
        ),
        sa.Column("lat", sa.Numeric(9, 5), nullable=True),
        sa.Column("lng", sa.Numeric(9, 5), nullable=True),
        sa.Column("store_id", sa.Integer(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("clicked_product_id", sa.Integer(), nullable=True),
        sa.Column("clicked_store_id", sa.Integer(), nullable=True),
        sa.Column("clicked_position", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_search_query_log_created_at"),
        "search_query_log",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_query_log_query_id"),
        "search_query_log",
        ["query_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_search_query_log_query_id"), table_name="search_query_log"
    )
    op.drop_index(
        op.f("ix_search_query_log_created_at"), table_name="search_query_log"
    )
    op.drop_table("search_query_log")
