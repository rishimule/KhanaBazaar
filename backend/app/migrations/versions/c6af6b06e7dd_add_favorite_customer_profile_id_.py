# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add favorite customer_profile_id created_at index

Revision ID: c6af6b06e7dd
Revises: 81ccebe49ed1
Create Date: 2026-05-22 20:12:36.033848

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6af6b06e7dd"
down_revision: Union[str, Sequence[str], None] = "81ccebe49ed1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_favorite_customer_created",
        "favorite",
        ["customer_profile_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_favorite_customer_created", table_name="favorite")
