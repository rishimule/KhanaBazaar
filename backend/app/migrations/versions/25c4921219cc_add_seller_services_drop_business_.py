"""add seller services drop business_category

Revision ID: 25c4921219cc
Revises: 4e1b8e2fbd9e
Create Date: 2026-05-03 12:27:18.713249

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25c4921219cc'
down_revision: Union[str, Sequence[str], None] = '4e1b8e2fbd9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create junction table
    op.create_table(
        "sellerprofile_service",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seller_profile_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["seller_profile_id"], ["sellerprofile.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["service.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "seller_profile_id", "service_id", name="uq_sellerprofile_service"
        ),
    )
    op.create_index(
        op.f("ix_sellerprofile_service_seller_profile_id"),
        "sellerprofile_service",
        ["seller_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sellerprofile_service_service_id"),
        "sellerprofile_service",
        ["service_id"],
        unique=False,
    )

    # 2. Backfill: every existing seller profile gets the grocery service.
    #    Skip if grocery service does not exist (clean DB before seed).
    op.execute(
        """
        INSERT INTO sellerprofile_service (created_at, updated_at, seller_profile_id, service_id)
        SELECT NOW(), NOW(), sp.id, s.id
        FROM sellerprofile sp
        CROSS JOIN service s
        WHERE s.slug = 'grocery'
        ON CONFLICT (seller_profile_id, service_id) DO NOTHING
        """
    )

    # 3. Drop business_category
    op.drop_column("sellerprofile", "business_category")

    # 4. Enforce 1 store per seller
    op.create_unique_constraint(
        "uq_store_seller_profile", "store", ["seller_profile_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_store_seller_profile", "store", type_="unique")
    op.add_column(
        "sellerprofile",
        sa.Column("business_category", sa.String(), nullable=True),
    )
    op.execute(
        "UPDATE sellerprofile SET business_category = 'Groceries' WHERE business_category IS NULL"
    )
    op.alter_column("sellerprofile", "business_category", nullable=False)
    op.drop_index(
        op.f("ix_sellerprofile_service_service_id"),
        table_name="sellerprofile_service",
    )
    op.drop_index(
        op.f("ix_sellerprofile_service_seller_profile_id"),
        table_name="sellerprofile_service",
    )
    op.drop_table("sellerprofile_service")
