"""make bank fields nullable on sellerprofile

Revision ID: eab47d66be16
Revises: 25c4921219cc
Create Date: 2026-05-03 17:00:48.233554

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eab47d66be16"
down_revision: Union[str, Sequence[str], None] = "25c4921219cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sellerprofile",
        "bank_account_number",
        existing_type=sa.String(),
        nullable=True,
    )
    op.alter_column(
        "sellerprofile",
        "bank_ifsc",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "sellerprofile",
        "bank_ifsc",
        existing_type=sa.String(),
        nullable=False,
    )
    op.alter_column(
        "sellerprofile",
        "bank_account_number",
        existing_type=sa.String(),
        nullable=False,
    )
