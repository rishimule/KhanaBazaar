# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add rotated_hashes to auth_session

Revision ID: 9383edc91f22
Revises: f2b3f31f10a0
Create Date: 2026-07-17 14:49:10.684184

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9383edc91f22'
down_revision: Union[str, Sequence[str], None] = 'f2b3f31f10a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "auth_session",
        sa.Column(
            "rotated_hashes",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("auth_session", "rotated_hashes")
