# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""admin_catalog_is_active_image_brand_unit_indexes

Revision ID: eeb39ac86872
Revises: c1a7f5e9b3d2
Create Date: 2026-05-14 14:25:25.351221

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eeb39ac86872"
down_revision: Union[str, Sequence[str], None] = "c1a7f5e9b3d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. pg_trgm extension for trigram search indexes.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. Add columns nullable first so backfill is safe.
    op.add_column("category", sa.Column("image_url", sa.String(), nullable=True))
    op.add_column("category", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("subcategory", sa.Column("image_url", sa.String(), nullable=True))
    op.add_column("subcategory", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("masterproduct", sa.Column("brand", sa.String(), nullable=True))
    op.add_column("masterproduct", sa.Column("unit", sa.String(), nullable=True))
    op.add_column("masterproduct", sa.Column("is_active", sa.Boolean(), nullable=True))

    # 3. Backfill existing rows to active.
    op.execute("UPDATE category SET is_active = TRUE WHERE is_active IS NULL")
    op.execute("UPDATE subcategory SET is_active = TRUE WHERE is_active IS NULL")
    op.execute("UPDATE masterproduct SET is_active = TRUE WHERE is_active IS NULL")

    # 4. Lock down is_active to NOT NULL with default TRUE.
    op.alter_column("category", "is_active", nullable=False, server_default=sa.text("true"))
    op.alter_column("subcategory", "is_active", nullable=False, server_default=sa.text("true"))
    op.alter_column("masterproduct", "is_active", nullable=False, server_default=sa.text("true"))

    # 5. Indexes on is_active for filtered scans.
    op.create_index("ix_category_is_active", "category", ["is_active"])
    op.create_index("ix_subcategory_is_active", "subcategory", ["is_active"])
    op.create_index("ix_masterproduct_is_active", "masterproduct", ["is_active"])

    # 6. Drop old uniques on slug — replaced by partial uniques below.
    op.drop_constraint("uq_category_service_slug", "category", type_="unique")
    op.drop_constraint("uq_subcategory_category_slug", "subcategory", type_="unique")
    # masterproduct.slug had a column-level unique constraint and index.
    op.drop_index("ix_masterproduct_slug", table_name="masterproduct")
    op.execute("ALTER TABLE masterproduct DROP CONSTRAINT IF EXISTS masterproduct_slug_key")
    # Recreate non-unique index for slug lookups.
    op.create_index("ix_masterproduct_slug", "masterproduct", ["slug"])

    # 7. Partial unique indexes — slug unique per parent only when active.
    op.create_index(
        "uq_category_service_slug_active",
        "category",
        ["service_id", "slug"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
    )
    op.create_index(
        "uq_subcategory_category_slug_active",
        "subcategory",
        ["category_id", "slug"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
    )
    op.create_index(
        "uq_masterproduct_subcategory_slug_active",
        "masterproduct",
        ["subcategory_id", "slug"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
    )

    # 8. Composite indexes for filtered list queries.
    op.create_index("ix_category_service_active", "category", ["service_id", "is_active"])
    op.create_index("ix_subcategory_category_active", "subcategory", ["category_id", "is_active"])
    op.create_index(
        "ix_masterproduct_subcategory_active", "masterproduct", ["subcategory_id", "is_active"]
    )

    # 9. Trigram GIN indexes for name + slug search.
    op.execute("CREATE INDEX ix_service_slug_trgm ON service USING GIN (slug gin_trgm_ops)")
    op.execute("CREATE INDEX ix_category_slug_trgm ON category USING GIN (slug gin_trgm_ops)")
    op.execute("CREATE INDEX ix_subcategory_slug_trgm ON subcategory USING GIN (slug gin_trgm_ops)")
    op.execute(
        "CREATE INDEX ix_masterproduct_slug_trgm ON masterproduct USING GIN (slug gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_service_translation_name_trgm "
        "ON service_translation USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_category_translation_name_trgm "
        "ON category_translation USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_subcategory_translation_name_trgm "
        "ON subcategory_translation USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_masterproduct_translation_name_trgm "
        "ON masterproduct_translation USING GIN (name gin_trgm_ops)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_masterproduct_translation_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_subcategory_translation_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_category_translation_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_service_translation_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_masterproduct_slug_trgm")
    op.execute("DROP INDEX IF EXISTS ix_subcategory_slug_trgm")
    op.execute("DROP INDEX IF EXISTS ix_category_slug_trgm")
    op.execute("DROP INDEX IF EXISTS ix_service_slug_trgm")
    op.drop_index("ix_masterproduct_subcategory_active", table_name="masterproduct")
    op.drop_index("ix_subcategory_category_active", table_name="subcategory")
    op.drop_index("ix_category_service_active", table_name="category")
    op.drop_index("uq_masterproduct_subcategory_slug_active", table_name="masterproduct")
    op.drop_index("uq_subcategory_category_slug_active", table_name="subcategory")
    op.drop_index("uq_category_service_slug_active", table_name="category")
    op.drop_index("ix_masterproduct_slug", table_name="masterproduct")
    op.create_index("ix_masterproduct_slug", "masterproduct", ["slug"], unique=True)
    op.create_unique_constraint(
        "uq_subcategory_category_slug", "subcategory", ["category_id", "slug"]
    )
    op.create_unique_constraint(
        "uq_category_service_slug", "category", ["service_id", "slug"]
    )
    op.drop_index("ix_masterproduct_is_active", table_name="masterproduct")
    op.drop_index("ix_subcategory_is_active", table_name="subcategory")
    op.drop_index("ix_category_is_active", table_name="category")
    op.drop_column("masterproduct", "is_active")
    op.drop_column("masterproduct", "unit")
    op.drop_column("masterproduct", "brand")
    op.drop_column("subcategory", "is_active")
    op.drop_column("subcategory", "image_url")
    op.drop_column("category", "is_active")
    op.drop_column("category", "image_url")
    # NOTE: pg_trgm extension intentionally left installed — other apps may use it.
