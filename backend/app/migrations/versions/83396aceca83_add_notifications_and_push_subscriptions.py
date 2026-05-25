# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add notifications and push subscriptions

Revision ID: 83396aceca83
Revises: c6af6b06e7dd
Create Date: 2026-05-25 01:30:36.855621

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '83396aceca83'
down_revision: Union[str, Sequence[str], None] = 'c6af6b06e7dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pushsubscription',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('customer_profile_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('p256dh', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('auth', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_agent', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_profile_id'], ['customerprofile.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_pushsubscription_customer_profile_id'),
        'pushsubscription', ['customer_profile_id'], unique=False,
    )
    op.create_index(
        op.f('ix_pushsubscription_endpoint'),
        'pushsubscription', ['endpoint'], unique=True,
    )
    op.create_table(
        'notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('customer_profile_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('type', sa.Enum('OrderStatus', name='notificationtype'), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('body', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('status_value', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('read', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['customer_profile_id'], ['customerprofile.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['order.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_notification_customer_created',
        'notification', ['customer_profile_id', 'created_at'], unique=False,
    )
    op.create_index(
        op.f('ix_notification_customer_profile_id'),
        'notification', ['customer_profile_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_notification_customer_profile_id'), table_name='notification')
    op.drop_index('ix_notification_customer_created', table_name='notification')
    op.drop_table('notification')
    op.drop_index(op.f('ix_pushsubscription_endpoint'), table_name='pushsubscription')
    op.drop_index(op.f('ix_pushsubscription_customer_profile_id'), table_name='pushsubscription')
    op.drop_table('pushsubscription')
    sa.Enum(name='notificationtype').drop(op.get_bind(), checkfirst=True)
