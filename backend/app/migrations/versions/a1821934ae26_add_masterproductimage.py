# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add masterproductimage table + backfill cover rows

Revision ID: a1821934ae26
Revises: 354c7943ff95
Create Date: 2026-06-09 00:00:00.000000

Adds the per-product image collection. Backfills one position-0 row
(source='external') from each product's existing image_url so current
covers immediately appear as the cover + first gallery entry. Additive,
zero-downtime; the image_url column is retained as a cover cache.
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1821934ae26"
down_revision: Union[str, Sequence[str], None] = "354c7943ff95"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "masterproductimage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("master_product_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("storage_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["master_product_id"], ["masterproduct.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_masterproductimage_master_product_id"),
        "masterproductimage",
        ["master_product_id"],
        unique=False,
    )
    # Backfill: one position-0 external row per product that has an image_url.
    op.execute(
        """
        INSERT INTO masterproductimage
            (master_product_id, position, url, source, storage_key, created_at, updated_at)
        SELECT id, 0, image_url, 'external', NULL, now(), now()
        FROM masterproduct
        WHERE image_url IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM masterproductimage i
              WHERE i.master_product_id = masterproduct.id
          )
        """
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_masterproductimage_master_product_id"),
        table_name="masterproductimage",
    )
    op.drop_table("masterproductimage")
