"""store_delivery_radius_pin_confirmed

Revision ID: cecb3aa39b17
Revises: 3e36788adecf
Create Date: 2026-05-06 22:28:45.046500

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'cecb3aa39b17'
down_revision: Union[str, Sequence[str], None] = '3e36788adecf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'store',
        sa.Column(
            'delivery_radius_km', sa.Float(), nullable=False,
            server_default=sa.text("5.0"),
        ),
    )
    op.add_column(
        'store',
        sa.Column(
            'pin_confirmed', sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column('store', 'pin_confirmed')
    op.drop_column('store', 'delivery_radius_km')
