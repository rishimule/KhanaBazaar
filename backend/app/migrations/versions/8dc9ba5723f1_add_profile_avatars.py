# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add profile avatars

Revision ID: 8dc9ba5723f1
Revises: a1821934ae26
Create Date: 2026-06-10 11:47:50.173311

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8dc9ba5723f1'
down_revision: Union[str, Sequence[str], None] = 'a1821934ae26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add avatar columns to the profile tables + the avatar CR group value."""
    op.add_column("customerprofile", sa.Column("avatar_url", sa.String(), nullable=True))
    op.add_column("customerprofile", sa.Column("avatar_storage_key", sa.String(), nullable=True))
    op.add_column("sellerprofile", sa.Column("avatar_url", sa.String(), nullable=True))
    op.add_column("sellerprofile", sa.Column("avatar_storage_key", sa.String(), nullable=True))
    # Native PG enum `sellerprofilechangegroup` stores the member VALUE. Add the
    # new member so avatar change-requests can be inserted. The value is only
    # USED after this migration commits, which PG 15 permits in-transaction.
    op.execute("ALTER TYPE sellerprofilechangegroup ADD VALUE IF NOT EXISTS 'avatar'")


def downgrade() -> None:
    """Drop the avatar columns (PG cannot easily DROP an enum value)."""
    op.drop_column("sellerprofile", "avatar_storage_key")
    op.drop_column("sellerprofile", "avatar_url")
    op.drop_column("customerprofile", "avatar_storage_key")
    op.drop_column("customerprofile", "avatar_url")
    # 'avatar' is intentionally left in sellerprofilechangegroup — PG has no
    # safe DROP VALUE, and leaving it is harmless.
