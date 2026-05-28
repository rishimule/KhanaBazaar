# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""seller profile change request

Revision ID: 4e5739351677
Revises: 7f3a9c2e1b04
Create Date: 2026-05-28 13:21:05.136760

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "4e5739351677"
down_revision = "7f3a9c2e1b04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cr_group = postgresql.ENUM(
        "identity", "address", "legal", "banking", "services", "store_basics",
        name="sellerprofilechangegroup", create_type=False,
    )
    cr_status = postgresql.ENUM(
        "submitted", "changes_requested", "approved", "rejected", "withdrawn",
        name="sellerprofilechangestatus", create_type=False,
    )
    cr_event_kind = postgresql.ENUM(
        "submitted", "resubmitted", "changes_requested",
        "approved", "approved_with_edits", "rejected", "withdrawn",
        name="sellerprofilechangeeventkind", create_type=False,
    )
    cr_group.create(op.get_bind(), checkfirst=True)
    cr_status.create(op.get_bind(), checkfirst=True)
    cr_event_kind.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "seller_profile_change_request",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("seller_profile_id", sa.Integer, sa.ForeignKey("sellerprofile.id"), nullable=False),
        sa.Column("group", cr_group, nullable=False),
        sa.Column("status", cr_status, nullable=False),
        sa.Column("proposed_json", postgresql.JSONB, nullable=False),
        sa.Column("applied_json", postgresql.JSONB, nullable=True),
        sa.Column("baseline_json", postgresql.JSONB, nullable=False),
        sa.Column("admin_note", sa.Text, nullable=True),
        sa.Column("submission_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=True),
    )
    op.create_index(
        "ix_seller_profile_change_request_seller_profile_id",
        "seller_profile_change_request", ["seller_profile_id"],
    )
    op.create_index(
        "ix_seller_profile_cr_seller_created",
        "seller_profile_change_request", ["seller_profile_id", "created_at"],
    )
    op.execute(
        'CREATE UNIQUE INDEX uq_seller_profile_cr_open '
        'ON seller_profile_change_request (seller_profile_id, "group") '
        "WHERE status IN ('submitted', 'changes_requested')"
    )

    op.create_table(
        "seller_profile_change_request_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "change_request_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("seller_profile_change_request.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", cr_event_kind, nullable=False),
        sa.Column("actor_user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False),
        sa.Column("actor_role", sa.String(length=16), nullable=False),
        sa.Column("payload_json", postgresql.JSONB, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_seller_profile_change_request_event_change_request_id",
        "seller_profile_change_request_event", ["change_request_id"],
    )
    op.create_index(
        "ix_seller_profile_cr_event_cr_created",
        "seller_profile_change_request_event", ["change_request_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_seller_profile_cr_event_cr_created", table_name="seller_profile_change_request_event")
    op.drop_index("ix_seller_profile_change_request_event_change_request_id", table_name="seller_profile_change_request_event")
    op.drop_table("seller_profile_change_request_event")
    op.execute("DROP INDEX IF EXISTS uq_seller_profile_cr_open")
    op.drop_index("ix_seller_profile_cr_seller_created", table_name="seller_profile_change_request")
    op.drop_index("ix_seller_profile_change_request_seller_profile_id", table_name="seller_profile_change_request")
    op.drop_table("seller_profile_change_request")
    op.execute("DROP TYPE IF EXISTS sellerprofilechangeeventkind")
    op.execute("DROP TYPE IF EXISTS sellerprofilechangestatus")
    op.execute("DROP TYPE IF EXISTS sellerprofilechangegroup")
