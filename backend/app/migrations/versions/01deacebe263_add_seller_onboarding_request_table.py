# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add seller_onboarding_request table

Revision ID: 01deacebe263
Revises: 68874265d516
Create Date: 2026-06-29 13:28:50.916097

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '01deacebe263'
down_revision: Union[str, Sequence[str], None] = '68874265d516'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "seller_onboarding_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("store_name", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("contact_phone", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("contact_email", sqlmodel.sql.sqltypes.AutoString(length=254), nullable=False),
        sa.Column("contact_address", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("preferred_categories", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
        sa.Column("area_lat", sa.Float(), nullable=True),
        sa.Column("area_lng", sa.Float(), nullable=True),
        sa.Column("area_label", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=True),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=True),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("new", "contacted", "onboarded", "dismissed", name="onboardingrequeststatus"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_seller_onboarding_request_submitted_by_user_id"),
        "seller_onboarding_request",
        ["submitted_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_seller_onboarding_request_submitted_by_user_id"),
        table_name="seller_onboarding_request",
    )
    op.drop_table("seller_onboarding_request")
    sa.Enum(name="onboardingrequeststatus").drop(op.get_bind(), checkfirst=True)
