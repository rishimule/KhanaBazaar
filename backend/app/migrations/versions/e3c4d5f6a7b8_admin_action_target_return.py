# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""admin action target type: return

Revision ID: e3c4d5f6a7b8
Revises: d2b3c4e5f6a7
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op

revision: str = "e3c4d5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "d2b3c4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `adminactiontargettype` stores enum member NAMES (PascalCase), so add
    # 'Return'. IF NOT EXISTS makes it idempotent; PG15 allows ADD VALUE inside
    # the tx because the label is not referenced by this migration.
    op.execute(
        "ALTER TYPE adminactiontargettype ADD VALUE IF NOT EXISTS 'Return'"
    )


def downgrade() -> None:
    # No PG DROP VALUE — the added enum label remains (harmless).
    pass
