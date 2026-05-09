# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""orders indexes and address snapshot

Revision ID: 4e1b8e2fbd9e
Revises: 20260425reset
Create Date: 2026-05-02 08:52:18.549145

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4e1b8e2fbd9e'
down_revision: Union[str, None] = '20260425reset'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_order_store_status",
        "order",
        ["store_id", "status"],
    )
    op.create_index(
        "ix_order_customer_status",
        "order",
        ["customer_profile_id", "status"],
    )
    op.add_column(
        "order",
        sa.Column(
            "delivery_address_snapshot",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
    op.alter_column("order", "delivery_address_snapshot", server_default=None)

    # Recreate orderitem.inventory_id FK with ON DELETE SET NULL so order
    # history survives if a seller removes an inventory row. Use direct
    # DDL on Postgres — batch_alter_table is for SQLite-style table rebuilds
    # and silently rebuilds the table here, dropping defaults.
    op.alter_column("orderitem", "inventory_id", existing_type=sa.Integer(), nullable=True)
    op.drop_constraint("orderitem_inventory_id_fkey", "orderitem", type_="foreignkey")
    op.create_foreign_key(
        "orderitem_inventory_id_fkey",
        "orderitem",
        "storeinventory",
        ["inventory_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("orderitem_inventory_id_fkey", "orderitem", type_="foreignkey")
    op.create_foreign_key(
        "orderitem_inventory_id_fkey",
        "orderitem",
        "storeinventory",
        ["inventory_id"],
        ["id"],
    )
    op.alter_column("orderitem", "inventory_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("order", "delivery_address_snapshot")
    op.drop_index("ix_order_customer_status", table_name="order")
    op.drop_index("ix_order_store_status", table_name="order")
