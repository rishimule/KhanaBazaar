"""schema reset baseline

Destructive local/pre-production reset migration. This revision drops the
current development schema objects and recreates the schema baseline modeled
on new_schema.sql plus compatibility fields required by current app flows.

Revision ID: 20260425reset
Revises: abc123456789
Create Date: 2026-04-30 11:40:44.087625

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260425reset"
down_revision: Union[str, Sequence[str], None] = "abc123456789"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_TABLES = (
    "storeinventory",
    "store",
    "sellerprofile",
    "masterproduct",
    "category",
    "item",
    "user",
)

_OLD_ENUMS = ("userrole", "verificationstatus")


_NEW_ENUMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("userrole", ("Customer", "Seller", "Admin")),
    ("verificationstatus", ("Pending", "Approved", "Rejected")),
    (
        "orderstatus",
        ("Pending", "Paid", "Packed", "Dispatched", "Delivered", "Cancelled"),
    ),
    ("paymentmethod", ("Upi", "Cash")),
    ("paymentstatus", ("Pending", "Paid", "Failed", "Refunded")),
    (
        "deliverystatus",
        ("Pending", "Packed", "Dispatched", "Delivered", "Cancelled"),
    ),
)


def upgrade() -> None:
    """Upgrade schema (destructive reset)."""
    for table_name in _OLD_TABLES:
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))

    bind = op.get_bind()
    existing = {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT typname FROM pg_type WHERE typname IN "
                "('userrole','verificationstatus','orderstatus',"
                "'paymentmethod','paymentstatus','deliverystatus')"
            )
        ).all()
    }
    for enum_name, values in _NEW_ENUMS:
        if enum_name in existing:
            continue
        quoted = ", ".join(f"'{value}'" for value in values)
        op.execute(sa.text(f"CREATE TYPE {enum_name} AS ENUM ({quoted})"))

    op.create_table(
        "language",
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("native_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )

    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("hashed_password", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("Customer", "Seller", "Admin", name="userrole", create_type=False),
            nullable=False,
        ),
        sa.Column("preferred_language", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["preferred_language"], ["language.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)

    op.create_table(
        "address",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("address_line1", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("address_line2", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=True),
        sa.Column("landmark", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=True),
        sa.Column("city", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("state", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("pincode", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column("country", sqlmodel.sql.sqltypes.AutoString(length=60), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "customerprofile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("first_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("last_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("phone", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone", name="ix_customerprofile_phone"),
        sa.UniqueConstraint("user_id", name="ix_customerprofile_user"),
    )

    op.create_table(
        "adminprofile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("first_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("last_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("phone", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column("employee_code", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("department", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_code"),
        sa.UniqueConstraint("phone", name="ix_adminprofile_phone"),
        sa.UniqueConstraint("user_id", name="ix_adminprofile_user"),
    )

    op.create_table(
        "sellerprofile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("first_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("last_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("phone", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("business_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("business_category", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("gst_number", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("fssai_license", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("bank_account_number", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("bank_ifsc", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "verification_status",
            postgresql.ENUM(
                "Pending",
                "Approved",
                "Rejected",
                name="verificationstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("rejection_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("business_address_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["business_address_id"], ["address.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone", name="ix_sellerprofile_phone"),
        sa.UniqueConstraint("user_id", name="uq_sellerprofile_user"),
    )
    op.create_index(
        op.f("ix_sellerprofile_business_address_id"),
        "sellerprofile",
        ["business_address_id"],
        unique=False,
    )

    op.create_table(
        "customeraddress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_profile_id", sa.Integer(), nullable=False),
        sa.Column("address_id", sa.Integer(), nullable=False),
        sa.Column("label", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["address_id"], ["address.id"]),
        sa.ForeignKeyConstraint(["customer_profile_id"], ["customerprofile.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "customer_profile_id",
            "address_id",
            name="uq_customeraddress_customer_address",
        ),
    )
    op.create_index(
        op.f("ix_customeraddress_customer_profile_id"),
        "customeraddress",
        ["customer_profile_id"],
        unique=False,
    )

    op.create_table(
        "service",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("icon_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_service_slug"), "service", ["slug"], unique=True)

    op.create_table(
        "service_translation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("language_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["language_code"], ["language.code"]),
        sa.ForeignKeyConstraint(["service_id"], ["service.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "language_code", name="uq_service_translation"),
    )

    op.create_table(
        "category",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["service.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "slug", name="uq_category_service_slug"),
    )
    op.create_index(op.f("ix_category_service_id"), "category", ["service_id"], unique=False)

    op.create_table(
        "category_translation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("language_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.ForeignKeyConstraint(["language_code"], ["language.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "language_code", name="uq_category_translation"),
    )

    op.create_table(
        "subcategory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "slug", name="uq_subcategory_category_slug"),
    )
    op.create_index(op.f("ix_subcategory_category_id"), "subcategory", ["category_id"], unique=False)

    op.create_table(
        "subcategory_translation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subcategory_id", sa.Integer(), nullable=False),
        sa.Column("language_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["language_code"], ["language.code"]),
        sa.ForeignKeyConstraint(["subcategory_id"], ["subcategory.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subcategory_id", "language_code", name="uq_subcategory_translation"),
    )

    op.create_table(
        "masterproduct",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subcategory_id", sa.Integer(), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("image_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("base_price", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["subcategory_id"], ["subcategory.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_masterproduct_slug"), "masterproduct", ["slug"], unique=True)
    op.create_index(
        op.f("ix_masterproduct_subcategory_id"),
        "masterproduct",
        ["subcategory_id"],
        unique=False,
    )

    op.create_table(
        "masterproduct_translation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("master_product_id", sa.Integer(), nullable=False),
        sa.Column("language_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["language_code"], ["language.code"]),
        sa.ForeignKeyConstraint(["master_product_id"], ["masterproduct.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "master_product_id", "language_code", name="uq_masterproduct_translation"
        ),
    )

    op.create_table(
        "store",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("seller_profile_id", sa.Integer(), nullable=False),
        sa.Column("address_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["address_id"], ["address.id"]),
        sa.ForeignKeyConstraint(["seller_profile_id"], ["sellerprofile.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_store_address_id"), "store", ["address_id"], unique=False)
    op.create_index(op.f("ix_store_name"), "store", ["name"], unique=False)
    op.create_index(
        op.f("ix_store_seller_profile_id"), "store", ["seller_profile_id"], unique=False
    )

    op.create_table(
        "storeinventory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["masterproduct.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "product_id", name="uq_store_product"),
    )

    op.create_table(
        "cart",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_profile_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["customer_profile_id"], ["customerprofile.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_profile_id", "store_id", name="uq_cart_customer_store"),
    )

    op.create_table(
        "cartitem",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cart_id", sa.Integer(), nullable=False),
        sa.Column("inventory_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["cart_id"], ["cart.id"]),
        sa.ForeignKeyConstraint(["inventory_id"], ["storeinventory.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cart_id", "inventory_id", name="uq_cartitem_cart_inventory"),
    )

    op.create_table(
        "order",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_profile_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("delivery_address_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "Pending",
                "Paid",
                "Packed",
                "Dispatched",
                "Delivered",
                "Cancelled",
                name="orderstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("subtotal", sa.Float(), nullable=False),
        sa.Column("delivery_fee", sa.Float(), nullable=False),
        sa.Column("tax", sa.Float(), nullable=False),
        sa.Column("total", sa.Float(), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_profile_id"], ["customerprofile.id"]),
        sa.ForeignKeyConstraint(["delivery_address_id"], ["address.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_order_customer_profile_id"), "order", ["customer_profile_id"], unique=False
    )
    op.create_index(op.f("ix_order_status"), "order", ["status"], unique=False)
    op.create_index(op.f("ix_order_store_id"), "order", ["store_id"], unique=False)

    op.create_table(
        "orderitem",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("inventory_id", sa.Integer(), nullable=False),
        sa.Column("product_name_snapshot", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("unit_price_snapshot", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["inventory_id"], ["storeinventory.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "inventory_id", name="uq_orderitem_order_inventory"),
    )

    op.create_table(
        "payment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column(
            "method",
            postgresql.ENUM("Upi", "Cash", name="paymentmethod", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "Pending",
                "Paid",
                "Failed",
                "Refunded",
                name="paymentstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("gateway_txn_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_gateway_txn_id"), "payment", ["gateway_txn_id"], unique=True)
    op.create_index(op.f("ix_payment_order_id"), "payment", ["order_id"], unique=False)

    op.create_table(
        "delivery",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "Pending",
                "Packed",
                "Dispatched",
                "Delivered",
                "Cancelled",
                name="deliverystatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("packed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tracking_notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_delivery_order_id"), "delivery", ["order_id"], unique=True)

    op.create_table(
        "review",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_profile_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("store_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["customer_profile_id"], ["customerprofile.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["masterproduct.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_review_customer_profile_id"), "review", ["customer_profile_id"], unique=False
    )
    op.create_index(op.f("ix_review_product_id"), "review", ["product_id"], unique=False)
    op.create_index(op.f("ix_review_store_id"), "review", ["store_id"], unique=False)

    op.create_table(
        "favorite",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_profile_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_profile_id"], ["customerprofile.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["masterproduct.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_profile_id", "product_id", name="uq_favorite_customer_product"),
    )

    op.create_index(
        "uq_customeraddress_one_default",
        "customeraddress",
        ["customer_profile_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )
    op.create_check_constraint(
        "ck_review_one_target",
        "review",
        "(product_id IS NOT NULL) != (store_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_review_rating_range",
        "review",
        "rating >= 1 AND rating <= 5",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_review_rating_range", "review", type_="check")
    op.drop_constraint("ck_review_one_target", "review", type_="check")
    op.drop_index("uq_customeraddress_one_default", table_name="customeraddress")

    op.drop_table("favorite")
    op.drop_index(op.f("ix_review_store_id"), table_name="review")
    op.drop_index(op.f("ix_review_product_id"), table_name="review")
    op.drop_index(op.f("ix_review_customer_profile_id"), table_name="review")
    op.drop_table("review")
    op.drop_index(op.f("ix_delivery_order_id"), table_name="delivery")
    op.drop_table("delivery")
    op.drop_index(op.f("ix_payment_order_id"), table_name="payment")
    op.drop_index(op.f("ix_payment_gateway_txn_id"), table_name="payment")
    op.drop_table("payment")
    op.drop_table("orderitem")
    op.drop_index(op.f("ix_order_store_id"), table_name="order")
    op.drop_index(op.f("ix_order_status"), table_name="order")
    op.drop_index(op.f("ix_order_customer_profile_id"), table_name="order")
    op.drop_table("order")
    op.drop_table("cartitem")
    op.drop_table("cart")
    op.drop_table("storeinventory")
    op.drop_index(op.f("ix_store_seller_profile_id"), table_name="store")
    op.drop_index(op.f("ix_store_name"), table_name="store")
    op.drop_index(op.f("ix_store_address_id"), table_name="store")
    op.drop_table("store")
    op.drop_table("masterproduct_translation")
    op.drop_index(op.f("ix_masterproduct_subcategory_id"), table_name="masterproduct")
    op.drop_index(op.f("ix_masterproduct_slug"), table_name="masterproduct")
    op.drop_table("masterproduct")
    op.drop_table("subcategory_translation")
    op.drop_index(op.f("ix_subcategory_category_id"), table_name="subcategory")
    op.drop_table("subcategory")
    op.drop_table("category_translation")
    op.drop_index(op.f("ix_category_service_id"), table_name="category")
    op.drop_table("category")
    op.drop_table("service_translation")
    op.drop_index(op.f("ix_service_slug"), table_name="service")
    op.drop_table("service")
    op.drop_index(op.f("ix_customeraddress_customer_profile_id"), table_name="customeraddress")
    op.drop_table("customeraddress")
    op.drop_index(op.f("ix_sellerprofile_business_address_id"), table_name="sellerprofile")
    op.drop_table("sellerprofile")
    op.drop_table("adminprofile")
    op.drop_table("customerprofile")
    op.drop_table("address")
    op.drop_index(op.f("ix_user_email"), table_name="user")
    op.drop_table("user")
    op.drop_table("language")

    for enum_name in (
        "deliverystatus",
        "paymentstatus",
        "paymentmethod",
        "orderstatus",
        "verificationstatus",
        "userrole",
    ):
        op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name} CASCADE"))


