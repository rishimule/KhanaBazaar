# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Drop firebase_uid, make email required and unique

Revision ID: a1b2c3d4e5f6
Revises: 87e918bfa062
Create Date: 2026-04-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '87e918bfa062'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_user_firebase_uid", table_name="user")
    op.drop_column("user", "firebase_uid")
    op.alter_column("user", "email", nullable=False)
    op.create_unique_constraint("uq_user_email", "user", ["email"])


def downgrade() -> None:
    op.drop_constraint("uq_user_email", "user", type_="unique")
    op.alter_column("user", "email", nullable=True)
    op.add_column(
        "user",
        sa.Column("firebase_uid", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    op.create_index("ix_user_firebase_uid", "user", ["firebase_uid"], unique=True)
