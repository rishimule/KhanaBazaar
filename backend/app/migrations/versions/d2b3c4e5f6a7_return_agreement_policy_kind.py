# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""return agreement policy kind

Revision ID: d2b3c4e5f6a7
Revises: c1a2b3d4e5f6
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d2b3c4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "c1a2b3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `policykind` stores lowercase member names. IF NOT EXISTS makes this
    # idempotent; PG15 allows ADD VALUE inside the tx because the new label is
    # not referenced by any statement in this migration.
    op.execute("ALTER TYPE policykind ADD VALUE IF NOT EXISTS 'return_agreement'")


def downgrade() -> None:
    # No PG DROP VALUE — the added enum label remains (harmless).
    pass
