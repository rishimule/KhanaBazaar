<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Schema Reset Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current development database shape with a reset baseline modeled on `new_schema.sql`, while keeping current auth, seller onboarding, admin review, catalog, store, and inventory flows working.

**Architecture:** SQLModel remains the source of application metadata, Alembic owns the database reset baseline, and FastAPI endpoints expose compatibility wire models where the database is richer than the current frontend. Future commerce tables are created now but stay unused until dedicated cart/order/payment specs wire them into behavior.

**Tech Stack:** FastAPI, SQLModel, SQLAlchemy/Alembic, PostgreSQL 15, asyncpg, Pydantic, Pytest, Next.js TypeScript types.

---

## Scope Check

This is one implementation plan because the schema reset must land atomically: SQLModel metadata, Alembic DDL, API joins, tests, and seed data must agree in the same commit sequence. Cart, order, payment, delivery, review, favorite, and translation-management behavior remains out of scope; this plan creates those tables only.

## File Structure

- Modify: `backend/app/src/app/models/base.py` for `UserRole`, `BaseSchema`, and `User`.
- Modify: `backend/app/src/app/models/address.py` to replace the mixin-only module with a concrete `Address` table.
- Create: `backend/app/src/app/models/profile.py` for `CustomerProfile`, `CustomerAddress`, `AdminProfile`, `SellerProfile`, and `VerificationStatus`.
- Modify: `backend/app/src/app/models/seller.py` to re-export seller profile names during transition.
- Modify: `backend/app/src/app/models/catalog.py` for language, service, category, subcategory, product, and translation tables.
- Modify: `backend/app/src/app/models/store.py` for `Store.seller_profile_id`, `Store.address_id`, and inventory relationships.
- Create: `backend/app/src/app/models/commerce.py` for future cart/order/payment/delivery/review/favorite tables.
- Modify: `backend/app/src/app/models/__init__.py` and `backend/app/migrations/env.py` so Alembic sees every table.
- Modify: `backend/app/src/app/schemas/address.py`, `backend/app/src/app/schemas/sellers.py`, and `backend/app/src/app/schemas/stores.py` for compatibility wire formats.
- Modify: `backend/app/src/app/api/auth.py`, `backend/app/src/app/api/sellers.py`, `backend/app/src/app/api/stores.py`, and `backend/app/src/app/api/catalog.py`.
- Create: `backend/app/src/app/services/profiles.py` for display-name composition and role-profile lookup helpers.
- Modify: `backend/app/src/app/db/dev_seed.py` and `backend/app/scripts/seed_database.py`.
- Create: `backend/app/migrations/versions/20260425reset_schema_reset_baseline.py`.
- Modify tests under `backend/app/tests/`.
- Modify: `frontend/src/types/index.ts` to clarify these are API wire types, not exact SQLModel table shapes.

## Task 1: Add Schema Contract Tests

**Files:**
- Create: `backend/app/tests/test_schema_reset_models.py`
- Test: `backend/app/tests/test_schema_reset_models.py`

- [ ] **Step 1: Write failing tests for the new model contract**

Create `backend/app/tests/test_schema_reset_models.py`:

```python
from sqlalchemy import inspect

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    CategoryTranslation,
    Language,
    LanguageCode,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.commerce import (
    Cart,
    CartItem,
    Delivery,
    Favorite,
    Order,
    OrderItem,
    Payment,
    Review,
)
from app.models.profile import (
    AdminProfile,
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory


def test_core_enum_values_are_api_values() -> None:
    assert [role.value for role in UserRole] == ["customer", "seller", "admin"]
    assert [language.value for language in LanguageCode] == ["en", "hi", "mr", "gu", "pa"]
    assert [status.value for status in VerificationStatus] == ["pending", "approved", "rejected"]


def test_expected_tables_are_registered_in_metadata() -> None:
    expected = {
        "user",
        "language",
        "customerprofile",
        "adminprofile",
        "sellerprofile",
        "address",
        "customeraddress",
        "service",
        "service_translation",
        "category",
        "category_translation",
        "subcategory",
        "subcategory_translation",
        "masterproduct",
        "masterproduct_translation",
        "store",
        "storeinventory",
        "cart",
        "cartitem",
        "order",
        "orderitem",
        "payment",
        "delivery",
        "review",
        "favorite",
    }
    assert expected.issubset(User.metadata.tables.keys())


def test_new_schema_columns_are_present() -> None:
    user_columns = {column.name for column in inspect(User).columns}
    assert {"email", "hashed_password", "is_active", "role", "preferred_language"}.issubset(user_columns)
    assert "full_name" not in user_columns

    seller_columns = {column.name for column in inspect(SellerProfile).columns}
    assert {
        "user_id",
        "first_name",
        "last_name",
        "business_name",
        "business_category",
        "business_address_id",
        "verification_status",
    }.issubset(seller_columns)
    assert "address_line1" not in seller_columns

    product_columns = {column.name for column in inspect(MasterProduct).columns}
    assert {"subcategory_id", "slug", "image_url", "base_price"}.issubset(product_columns)
    assert "name" not in product_columns

    store_columns = {column.name for column in inspect(Store).columns}
    assert {"seller_profile_id", "address_id", "name", "is_active"}.issubset(store_columns)
    assert "seller_id" not in store_columns
    assert "address_line1" not in store_columns


def test_model_classes_are_imported() -> None:
    classes = [
        Address,
        CustomerProfile,
        CustomerAddress,
        AdminProfile,
        SellerProfile,
        Language,
        Service,
        ServiceTranslation,
        Category,
        CategoryTranslation,
        Subcategory,
        SubcategoryTranslation,
        MasterProduct,
        MasterProductTranslation,
        Store,
        StoreInventory,
        Cart,
        CartItem,
        Order,
        OrderItem,
        Payment,
        Delivery,
        Review,
        Favorite,
    ]
    assert all(model.__table__ is not None for model in classes)
```

- [ ] **Step 2: Run the model contract test and verify it fails**

Run:

```bash
cd backend/app
uv run pytest tests/test_schema_reset_models.py -q
```

Expected: fails with import errors for `app.models.profile`, `app.models.commerce`, or missing columns.

- [ ] **Step 3: Commit the failing contract test**

Run:

```bash
git add backend/app/tests/test_schema_reset_models.py
git commit -m "test(schema): add reset baseline model contract"
```

## Task 2: Implement SQLModel Table Models

**Files:**
- Modify: `backend/app/src/app/models/base.py`
- Modify: `backend/app/src/app/models/address.py`
- Create: `backend/app/src/app/models/profile.py`
- Modify: `backend/app/src/app/models/seller.py`
- Modify: `backend/app/src/app/models/catalog.py`
- Modify: `backend/app/src/app/models/store.py`
- Create: `backend/app/src/app/models/commerce.py`
- Modify: `backend/app/src/app/models/__init__.py`
- Modify: `backend/app/migrations/env.py`
- Test: `backend/app/tests/test_schema_reset_models.py`

- [ ] **Step 1: Replace `models/base.py` with the reset user model**

Use lowercase enum values and keep nullable `hashed_password`:

```python
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import DateTime, Field, SQLModel


class UserRole(str, enum.Enum):
    Customer = "customer"
    Seller = "seller"
    Admin = "admin"


class BaseSchema(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )


class UserBase(SQLModel):
    email: str = Field(index=True, unique=True, nullable=False)
    hashed_password: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True, nullable=False)
    role: UserRole = Field(default=UserRole.Customer, nullable=False)
    preferred_language: str = Field(default="en", foreign_key="language.code", nullable=False)


class User(BaseSchema, UserBase, table=True):
    pass
```

- [ ] **Step 2: Replace `models/address.py` with a concrete address table**

Keep the address field lengths aligned with existing validators:

```python
from typing import Optional

from sqlmodel import Field

from app.models.base import BaseSchema


class Address(BaseSchema, table=True):
    address_line1: str = Field(nullable=False, max_length=120)
    address_line2: Optional[str] = Field(default=None, nullable=True, max_length=120)
    landmark: Optional[str] = Field(default=None, nullable=True, max_length=120)
    city: str = Field(nullable=False, max_length=80)
    state: str = Field(nullable=False, max_length=80)
    pincode: str = Field(nullable=False, max_length=10)
    country: str = Field(nullable=False, default="India", max_length=60)
    latitude: Optional[float] = Field(default=None, nullable=True)
    longitude: Optional[float] = Field(default=None, nullable=True)
```

- [ ] **Step 3: Create `models/profile.py`**

Include `business_category` as the approved compatibility field:

```python
import enum
from datetime import date
from typing import Optional

from sqlmodel import Field, Relationship, UniqueConstraint

from app.models.address import Address
from app.models.base import BaseSchema, User


class VerificationStatus(str, enum.Enum):
    Pending = "pending"
    Approved = "approved"
    Rejected = "rejected"


class CustomerProfile(BaseSchema, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", name="ix_customerprofile_user"),
        UniqueConstraint("phone", name="ix_customerprofile_phone"),
    )
    user_id: int = Field(foreign_key="user.id", nullable=False)
    first_name: str = Field(nullable=False)
    last_name: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None, max_length=20)
    date_of_birth: Optional[date] = Field(default=None)
    gender: Optional[str] = Field(default=None)

    user: User = Relationship()


class CustomerAddress(BaseSchema, table=True):
    __tablename__ = "customeraddress"
    __table_args__ = (
        UniqueConstraint("customer_profile_id", "address_id", name="uq_customeraddress_customer_address"),
    )
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False, index=True)
    address_id: int = Field(foreign_key="address.id", nullable=False)
    label: Optional[str] = Field(default=None)
    is_default: bool = Field(default=False, nullable=False)

    customer_profile: CustomerProfile = Relationship()
    address: Address = Relationship()


class AdminProfile(BaseSchema, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", name="ix_adminprofile_user"),
        UniqueConstraint("phone", name="ix_adminprofile_phone"),
    )
    user_id: int = Field(foreign_key="user.id", nullable=False)
    first_name: str = Field(nullable=False)
    last_name: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None, max_length=20)
    employee_code: Optional[str] = Field(default=None, unique=True)
    department: Optional[str] = Field(default=None)

    user: User = Relationship()


class SellerProfile(BaseSchema, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_sellerprofile_user"),
        UniqueConstraint("phone", name="ix_sellerprofile_phone"),
    )
    user_id: int = Field(foreign_key="user.id", nullable=False)
    first_name: str = Field(nullable=False)
    last_name: Optional[str] = Field(default=None)
    phone: str = Field(nullable=False, max_length=20)
    business_name: str = Field(nullable=False)
    business_category: str = Field(nullable=False)
    gst_number: Optional[str] = Field(default=None)
    fssai_license: Optional[str] = Field(default=None)
    bank_account_number: str = Field(nullable=False)
    bank_ifsc: str = Field(nullable=False)
    verification_status: VerificationStatus = Field(default=VerificationStatus.Pending, nullable=False)
    rejection_reason: Optional[str] = Field(default=None)
    business_address_id: int = Field(foreign_key="address.id", nullable=False, index=True)

    user: User = Relationship()
    business_address: Address = Relationship()
```

- [ ] **Step 4: Make `models/seller.py` a compatibility re-export**

Replace the file with:

```python
from app.models.profile import SellerProfile, VerificationStatus

__all__ = ["SellerProfile", "VerificationStatus"]
```

- [ ] **Step 5: Replace `models/catalog.py` with multilingual catalog tables**

Use English translations in API compatibility reads:

```python
import enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint

from app.models.base import BaseSchema


class LanguageCode(str, enum.Enum):
    English = "en"
    Hindi = "hi"
    Marathi = "mr"
    Gujarati = "gu"
    Punjabi = "pa"


class Language(SQLModel, table=True):
    code: str = Field(primary_key=True)
    name: str = Field(nullable=False)
    native_name: str = Field(nullable=False)
    is_active: bool = Field(default=True, nullable=False)


class Service(BaseSchema, table=True):
    slug: str = Field(nullable=False, unique=True, index=True)
    icon_url: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True, nullable=False)
    sort_order: int = Field(default=0, nullable=False)


class ServiceTranslation(BaseSchema, table=True):
    __tablename__ = "service_translation"
    __table_args__ = (UniqueConstraint("service_id", "language_code", name="uq_service_translation"),)
    service_id: int = Field(foreign_key="service.id", nullable=False)
    language_code: str = Field(foreign_key="language.code", nullable=False)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)


class Category(BaseSchema, table=True):
    __table_args__ = (UniqueConstraint("service_id", "slug", name="uq_category_service_slug"),)
    service_id: int = Field(foreign_key="service.id", nullable=False, index=True)
    slug: str = Field(nullable=False)
    sort_order: int = Field(default=0, nullable=False)

    service: Service = Relationship()


class CategoryTranslation(BaseSchema, table=True):
    __tablename__ = "category_translation"
    __table_args__ = (UniqueConstraint("category_id", "language_code", name="uq_category_translation"),)
    category_id: int = Field(foreign_key="category.id", nullable=False)
    language_code: str = Field(foreign_key="language.code", nullable=False)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)


class Subcategory(BaseSchema, table=True):
    __table_args__ = (UniqueConstraint("category_id", "slug", name="uq_subcategory_category_slug"),)
    category_id: int = Field(foreign_key="category.id", nullable=False, index=True)
    slug: str = Field(nullable=False)
    sort_order: int = Field(default=0, nullable=False)


class SubcategoryTranslation(BaseSchema, table=True):
    __tablename__ = "subcategory_translation"
    __table_args__ = (UniqueConstraint("subcategory_id", "language_code", name="uq_subcategory_translation"),)
    subcategory_id: int = Field(foreign_key="subcategory.id", nullable=False)
    language_code: str = Field(foreign_key="language.code", nullable=False)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)


class MasterProduct(BaseSchema, table=True):
    subcategory_id: int = Field(foreign_key="subcategory.id", nullable=False, index=True)
    slug: str = Field(nullable=False, unique=True, index=True)
    image_url: Optional[str] = Field(default=None)
    base_price: float = Field(nullable=False)


class MasterProductTranslation(BaseSchema, table=True):
    __tablename__ = "masterproduct_translation"
    __table_args__ = (UniqueConstraint("master_product_id", "language_code", name="uq_masterproduct_translation"),)
    master_product_id: int = Field(foreign_key="masterproduct.id", nullable=False)
    language_code: str = Field(foreign_key="language.code", nullable=False)
    name: str = Field(nullable=False)
    description: str = Field(nullable=False)
```

- [ ] **Step 6: Replace `models/store.py`**

Seller ownership must now authorize through `SellerProfile.user_id`:

```python
from sqlmodel import Field, Relationship, UniqueConstraint

from app.models.address import Address
from app.models.base import BaseSchema
from app.models.catalog import MasterProduct
from app.models.profile import SellerProfile


class Store(BaseSchema, table=True):
    name: str = Field(index=True, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    seller_profile_id: int = Field(foreign_key="sellerprofile.id", nullable=False, index=True)
    address_id: int = Field(foreign_key="address.id", nullable=False, index=True)

    seller_profile: SellerProfile = Relationship()
    address: Address = Relationship()


class StoreInventory(BaseSchema, table=True):
    __table_args__ = (UniqueConstraint("store_id", "product_id", name="uq_store_product"),)
    store_id: int = Field(foreign_key="store.id", nullable=False)
    product_id: int = Field(foreign_key="masterproduct.id", nullable=False)
    price: float = Field(nullable=False)
    stock: int = Field(default=0, nullable=False)
    is_available: bool = Field(default=True, nullable=False)

    store: Store = Relationship()
    product: MasterProduct = Relationship()
```

- [ ] **Step 7: Create `models/commerce.py`**

Define future-ready tables without endpoints:

```python
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import DateTime, Field, UniqueConstraint

from app.models.base import BaseSchema


class OrderStatus(str, enum.Enum):
    Pending = "pending"
    Paid = "paid"
    Packed = "packed"
    Dispatched = "dispatched"
    Delivered = "delivered"
    Cancelled = "cancelled"


class PaymentMethod(str, enum.Enum):
    Upi = "upi"
    Cash = "cash"


class PaymentStatus(str, enum.Enum):
    Pending = "pending"
    Paid = "paid"
    Failed = "failed"
    Refunded = "refunded"


class DeliveryStatus(str, enum.Enum):
    Pending = "pending"
    Packed = "packed"
    Dispatched = "dispatched"
    Delivered = "delivered"
    Cancelled = "cancelled"


class Cart(BaseSchema, table=True):
    __table_args__ = (UniqueConstraint("customer_profile_id", "store_id", name="uq_cart_customer_store"),)
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False)
    store_id: int = Field(foreign_key="store.id", nullable=False)


class CartItem(BaseSchema, table=True):
    __tablename__ = "cartitem"
    __table_args__ = (UniqueConstraint("cart_id", "inventory_id", name="uq_cartitem_cart_inventory"),)
    cart_id: int = Field(foreign_key="cart.id", nullable=False)
    inventory_id: int = Field(foreign_key="storeinventory.id", nullable=False)
    quantity: int = Field(nullable=False)


class Order(BaseSchema, table=True):
    __tablename__ = "order"
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False, index=True)
    store_id: int = Field(foreign_key="store.id", nullable=False, index=True)
    delivery_address_id: int = Field(foreign_key="address.id", nullable=False)
    status: OrderStatus = Field(default=OrderStatus.Pending, nullable=False, index=True)
    subtotal: float = Field(nullable=False)
    delivery_fee: float = Field(nullable=False)
    tax: float = Field(nullable=False)
    total: float = Field(nullable=False)
    placed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_type=DateTime(timezone=True))


class OrderItem(BaseSchema, table=True):
    __tablename__ = "orderitem"
    __table_args__ = (UniqueConstraint("order_id", "inventory_id", name="uq_orderitem_order_inventory"),)
    order_id: int = Field(foreign_key="order.id", nullable=False)
    inventory_id: int = Field(foreign_key="storeinventory.id", nullable=False)
    product_name_snapshot: str = Field(nullable=False)
    unit_price_snapshot: float = Field(nullable=False)
    quantity: int = Field(nullable=False)
    line_total: float = Field(nullable=False)


class Payment(BaseSchema, table=True):
    order_id: int = Field(foreign_key="order.id", nullable=False, index=True)
    amount: float = Field(nullable=False)
    method: PaymentMethod = Field(default=PaymentMethod.Upi, nullable=False)
    status: PaymentStatus = Field(default=PaymentStatus.Pending, nullable=False)
    gateway_txn_id: Optional[str] = Field(default=None, unique=True, index=True)
    paid_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))


class Delivery(BaseSchema, table=True):
    order_id: int = Field(foreign_key="order.id", nullable=False, unique=True, index=True)
    status: DeliveryStatus = Field(default=DeliveryStatus.Pending, nullable=False)
    packed_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    dispatched_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    delivered_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    tracking_notes: Optional[str] = Field(default=None)


class Review(BaseSchema, table=True):
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False, index=True)
    product_id: Optional[int] = Field(default=None, foreign_key="masterproduct.id", index=True)
    store_id: Optional[int] = Field(default=None, foreign_key="store.id", index=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    rating: int = Field(nullable=False)
    comment: Optional[str] = Field(default=None)


class Favorite(BaseSchema, table=True):
    __table_args__ = (UniqueConstraint("customer_profile_id", "product_id", name="uq_favorite_customer_product"),)
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False)
    product_id: int = Field(foreign_key="masterproduct.id", nullable=False)
```

- [ ] **Step 8: Register all models for metadata**

Replace `backend/app/src/app/models/__init__.py` with imports for every model class. Update `backend/app/migrations/env.py` to import `app.models` instead of one or two individual modules:

```python
from app.models.base import BaseSchema
import app.models  # noqa: F401,E402

target_metadata = BaseSchema.metadata
```

- [ ] **Step 9: Run the model contract test and fix mapper/import errors**

Run:

```bash
cd backend/app
uv run pytest tests/test_schema_reset_models.py -q
```

Expected: all tests in `test_schema_reset_models.py` pass.

- [ ] **Step 10: Run backend lint on changed model files**

Run:

```bash
cd backend/app
uv run ruff check src/app/models tests/test_schema_reset_models.py
```

Expected: exit 0.

- [ ] **Step 11: Commit models**

Run:

```bash
git add backend/app/src/app/models backend/app/migrations/env.py
git commit -m "feat(schema): add reset baseline models"
```

## Task 3: Add Reset Baseline Alembic Migration

**Files:**
- Create: `backend/app/migrations/versions/20260425reset_schema_reset_baseline.py`
- Test: `backend/app/tests/test_schema_reset_models.py`

- [ ] **Step 1: Generate the migration**

Run:

```bash
cd backend/app
uv run alembic revision --rev-id 20260425reset --autogenerate -m "schema reset baseline"
```

Expected: `backend/app/migrations/versions/20260425reset_schema_reset_baseline.py` is created.

- [ ] **Step 2: Edit the migration header and upgrade strategy**

Open the new migration. Keep the generated revision identifiers. Replace the docstring body with this wording:

```python
"""schema reset baseline

Destructive local/pre-production reset migration. This revision drops the
current development schema objects and recreates the schema baseline modeled
on new_schema.sql plus compatibility fields required by current app flows.
"""
```

- [ ] **Step 3: Add manual constraints and indexes Alembic may miss**

In `upgrade()`, after generated table creation, add:

```python
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
op.create_check_constraint("ck_review_rating_range", "review", "rating >= 1 AND rating <= 5")
```

In `downgrade()`, drop these before dropping tables:

```python
op.drop_constraint("ck_review_rating_range", "review", type_="check")
op.drop_constraint("ck_review_one_target", "review", type_="check")
op.drop_index("uq_customeraddress_one_default", table_name="customeraddress")
```

- [ ] **Step 4: Ensure destructive reset handles old tables**

At the top of `upgrade()`, before creating new tables, drop old tables in dependency order:

```python
for table_name in (
    "storeinventory",
    "store",
    "sellerprofile",
    "masterproduct",
    "category",
    "item",
    "user",
):
    op.execute(sa.text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
```

Then drop old enum types if they are incompatible:

```python
for enum_name in ("userrole", "verificationstatus"):
    op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name} CASCADE"))
```

- [ ] **Step 5: Apply migration to a reset local database**

Run:

```bash
./scripts/reset_local_state.sh
```

Expected: script reaches `Local state reset complete.` after Alembic upgrade and seed. If seed fails because it still uses old models, continue to Task 6 before rerunning the full script.

- [ ] **Step 6: Run schema contract tests**

Run:

```bash
cd backend/app
uv run pytest tests/test_schema_reset_models.py -q
```

Expected: pass.

- [ ] **Step 7: Commit migration**

Run:

```bash
git add backend/app/migrations/versions
git commit -m "feat(schema): add reset baseline migration"
```

## Task 4: Add Profile and Address Compatibility Helpers

**Files:**
- Create: `backend/app/src/app/services/profiles.py`
- Modify: `backend/app/src/app/schemas/address.py`
- Test: `backend/app/tests/test_profile_helpers.py`

- [ ] **Step 1: Write helper tests**

Create `backend/app/tests/test_profile_helpers.py`:

```python
from app.services.profiles import compose_full_name, split_full_name


def test_split_full_name_splits_first_token_and_rest() -> None:
    assert split_full_name("Priya Verma") == ("Priya", "Verma")
    assert split_full_name("Ravi") == ("Ravi", None)
    assert split_full_name("  Sana   Kapoor  ") == ("Sana", "Kapoor")


def test_compose_full_name_skips_missing_last_name() -> None:
    assert compose_full_name("Priya", "Verma") == "Priya Verma"
    assert compose_full_name("Ravi", None) == "Ravi"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd backend/app
uv run pytest tests/test_profile_helpers.py -q
```

Expected: fails with `ModuleNotFoundError: No module named 'app.services.profiles'`.

- [ ] **Step 3: Create profile helper module**

Create `backend/app/src/app/services/profiles.py`:

```python
from typing import Optional


def split_full_name(full_name: str) -> tuple[str, Optional[str]]:
    parts = " ".join(full_name.strip().split()).split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) == 2 else None
    return first_name, last_name


def compose_full_name(first_name: str, last_name: Optional[str]) -> str:
    if last_name:
        return f"{first_name} {last_name}"
    return first_name
```

- [ ] **Step 4: Update address converters for concrete `Address` rows**

Replace the bottom converter functions in `backend/app/src/app/schemas/address.py` with:

```python
def address_from_payload(payload: AddressPayload) -> dict[str, object]:
    return {field: getattr(payload, field) for field in _ADDRESS_FIELDS}


def address_to_payload(owner: object) -> AddressPayload:
    return AddressPayload(**{field: getattr(owner, field) for field in _ADDRESS_FIELDS})
```

This keeps the public helper names stable. When owner objects now expose `.address` relationships, call `address_to_payload(store.address)` or `address_to_payload(profile.business_address)`.

- [ ] **Step 5: Run helper tests**

Run:

```bash
cd backend/app
uv run pytest tests/test_profile_helpers.py tests/test_address_validator.py -q
```

Expected: pass.

- [ ] **Step 6: Commit helper work**

Run:

```bash
git add backend/app/src/app/services/profiles.py backend/app/src/app/schemas/address.py backend/app/tests/test_profile_helpers.py
git commit -m "feat(schema): add profile compatibility helpers"
```

## Task 5: Update Auth and Seller APIs

**Files:**
- Modify: `backend/app/src/app/api/auth.py`
- Modify: `backend/app/src/app/api/sellers.py`
- Modify: `backend/app/src/app/schemas/sellers.py`
- Modify: `backend/app/tests/test_auth.py`
- Modify: `backend/app/tests/test_seller_register.py`
- Modify: `backend/app/tests/test_seller_status.py`
- Modify: `backend/app/tests/test_admin_applications.py`
- Modify: `backend/app/tests/test_admin_verify.py`

- [ ] **Step 1: Update auth tests to assert profile creation**

In `backend/app/tests/test_auth.py`, update new-user assertions:

```python
from sqlmodel import select
from app.models.profile import CustomerProfile

result = await session.exec(select(CustomerProfile))
profile = result.one()
assert profile.first_name == "New"
assert profile.last_name == "User"
assert data["user"]["full_name"] == "New User"
```

Update test user fixtures to create role profiles instead of passing `full_name` into `User`.

- [ ] **Step 2: Run auth tests and verify failure**

Run:

```bash
cd backend/app
uv run pytest tests/test_auth.py -q
```

Expected: fails where `auth.py` still writes `User.full_name`.

- [ ] **Step 3: Update seller schemas**

Keep wire fields stable:

```python
class SellerProfilePayload(BaseModel):
    id: int
    user_id: int
    full_name: str
    business_name: str
    business_category: str
    address: AddressPayload
    phone: str
    gst_number: str | None = None
    fssai_license: str | None = None
    bank_account_number: str
    bank_ifsc: str
    verification_status: str
    rejection_reason: Optional[str] = None
```

Keep `SellerRegisterBody`, `SellerProfileUpdateBody`, and `SellerApplicationPayload` request/response fields as they are today, with `full_name` on register/application responses.

- [ ] **Step 4: Update `auth.py`**

Use `split_full_name`, create role profiles, and compose user responses:

```python
from app.models.profile import CustomerProfile, SellerProfile
from app.models.address import Address
from app.services.profiles import compose_full_name, split_full_name
```

For new customer OTP verification:

```python
first_name, last_name = split_full_name(body.full_name)
user = User(email=email, role=UserRole.Customer)
session.add(user)
await session.flush()
profile = CustomerProfile(user_id=user.id, first_name=first_name, last_name=last_name)
session.add(profile)
await session.commit()
await session.refresh(user)
```

Return a compatibility user dict:

```python
user_payload = user.model_dump()
user_payload["full_name"] = body.full_name.strip()
```

For `/auth/me`, query the role profile and add `full_name` to the returned dict.

For seller registration:

```python
first_name, last_name = split_full_name(body.full_name)
user = User(email=email, role=UserRole.Seller)
session.add(user)
await session.flush()
address = Address(**address_from_payload(body.address))
session.add(address)
await session.flush()
profile = SellerProfile(
    user_id=user.id,
    first_name=first_name,
    last_name=last_name,
    business_name=body.business_name,
    business_category=body.business_category,
    phone=body.phone,
    gst_number=body.gst_number,
    fssai_license=body.fssai_license,
    bank_account_number=body.bank_account_number,
    bank_ifsc=body.bank_ifsc,
    business_address_id=address.id,
)
session.add(profile)
```

- [ ] **Step 5: Update `sellers.py`**

Use joins and relationships:

```python
from app.models.profile import SellerProfile, VerificationStatus
from app.services.profiles import compose_full_name, split_full_name
```

For profile payloads, use:

```python
full_name = compose_full_name(profile.first_name, profile.last_name)
address = address_to_payload(profile.business_address)
```

For profile update, update `first_name`, `last_name`, business fields, and mutate or replace the linked `Address` row from `address_from_payload(body.address)`.

- [ ] **Step 6: Run seller and auth tests**

Run:

```bash
cd backend/app
uv run pytest tests/test_auth.py tests/test_seller_register.py tests/test_seller_status.py tests/test_admin_applications.py tests/test_admin_verify.py -q
```

Expected: pass.

- [ ] **Step 7: Commit auth and seller API updates**

Run:

```bash
git add backend/app/src/app/api/auth.py backend/app/src/app/api/sellers.py backend/app/src/app/schemas/sellers.py backend/app/tests/test_auth.py backend/app/tests/test_seller_register.py backend/app/tests/test_seller_status.py backend/app/tests/test_admin_applications.py backend/app/tests/test_admin_verify.py
git commit -m "feat(schema): adapt auth and seller APIs"
```

## Task 6: Update Store and Catalog APIs

**Files:**
- Modify: `backend/app/src/app/api/stores.py`
- Modify: `backend/app/src/app/api/catalog.py`
- Modify: `backend/app/src/app/schemas/stores.py`
- Modify: `backend/app/tests/test_stores.py`

- [ ] **Step 1: Update store tests for seller profile ownership**

Create a seller profile and address for `mock_seller` in the store test fixture:

```python
from app.models.address import Address
from app.models.profile import SellerProfile, VerificationStatus

address = Address(**make_address())
session.add(address)
await session.flush()
profile = SellerProfile(
    user_id=mock_seller.id,
    first_name="Seller",
    last_name=None,
    business_name="Seller Store",
    business_category="grocery",
    phone="+919811110000",
    gst_number="06AAAAA1111A1Z1",
    fssai_license="44556677889900",
    bank_account_number="80100200300700",
    bank_ifsc="HDFC0000001",
    verification_status=VerificationStatus.Approved,
    business_address_id=address.id,
)
session.add(profile)
```

- [ ] **Step 2: Run store tests and verify failure**

Run:

```bash
cd backend/app
uv run pytest tests/test_stores.py -q
```

Expected: fails where `stores.py` still uses `Store.seller_id` and `Store` flat address columns.

- [ ] **Step 3: Update store API**

Add helpers:

```python
async def _seller_profile_for_user(session: AsyncSession, user_id: int) -> SellerProfile:
    result = await session.exec(select(SellerProfile).where(SellerProfile.user_id == user_id))
    profile = result.first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    return profile
```

Update `_store_read`:

```python
return StoreRead(
    id=store.id,
    name=store.name,
    address=address_to_payload(store.address),
    is_active=store.is_active,
    seller_id=store.seller_profile.user_id,
    created_at=store.created_at.isoformat(),
    updated_at=store.updated_at.isoformat(),
)
```

Update store creation:

```python
seller_profile = await _seller_profile_for_user(session, seller.id)
address = Address(**address_from_payload(payload.address))
session.add(address)
await session.flush()
store = Store(name=payload.name, seller_profile_id=seller_profile.id, address_id=address.id)
```

Update authorization checks from `store.seller_id != seller.id` to `store.seller_profile.user_id != seller.id`.

- [ ] **Step 4: Update catalog API compatibility responses**

Create Pydantic compatibility schemas inside `schemas` or `api/catalog.py`:

```python
class CategoryRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    name: str
    description: str | None = None


class ProductRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    name: str
    description: str
    category_id: int
    image_url: str | None = None
    base_price: float
```

For list endpoints, join English translations and map products back to their parent category id through subcategory:

```python
stmt = (
    select(MasterProduct, MasterProductTranslation, Subcategory)
    .join(MasterProductTranslation, MasterProductTranslation.master_product_id == MasterProduct.id)
    .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)
    .where(MasterProductTranslation.language_code == "en")
)
```

For create category/product endpoints, create base rows plus English translation rows.

- [ ] **Step 5: Run store/catalog tests**

Run:

```bash
cd backend/app
uv run pytest tests/test_stores.py -q
```

Expected: pass.

- [ ] **Step 6: Commit store and catalog API updates**

Run:

```bash
git add backend/app/src/app/api/stores.py backend/app/src/app/api/catalog.py backend/app/src/app/schemas/stores.py backend/app/tests/test_stores.py
git commit -m "feat(schema): adapt store and catalog APIs"
```

## Task 7: Update Canonical Seed

**Files:**
- Modify: `backend/app/src/app/db/dev_seed.py`
- Modify: `backend/app/scripts/seed_database.py`
- Test: `backend/app/tests/test_dev_seed.py`
- Test: `backend/app/tests/test_local_reset.py`

- [ ] **Step 1: Update seed expected counts**

Use these counts:

```python
EXPECTED_FULL_COUNTS = {
    "users": 8,
    "language": 5,
    "customerprofile": 1,
    "adminprofile": 1,
    "sellerprofile": 6,
    "address": 9,
    "service": 1,
    "service_translation": 1,
    "category": 4,
    "category_translation": 4,
    "subcategory": 4,
    "subcategory_translation": 4,
    "masterproduct": 12,
    "masterproduct_translation": 12,
    "store": 3,
    "storeinventory": 26,
}
```

- [ ] **Step 2: Update seed upsert helpers**

Create helpers in `dev_seed.py`:

```python
async def _upsert_address(session: AsyncSession, data: Mapping[str, Any]) -> Address:
    address = Address(**{key: data[key] for key in _ADDRESS_KEYS})
    session.add(address)
    await session.flush()
    return address


async def _upsert_language(session: AsyncSession, code: str, name: str, native_name: str) -> Language:
    existing = await session.get(Language, code)
    language = existing or Language(code=code, name=name, native_name=native_name, is_active=True)
    language.name = name
    language.native_name = native_name
    language.is_active = True
    session.add(language)
    await session.flush()
    return language
```

Seed profiles by splitting full names with `split_full_name`. Seed catalog rows as service, category, subcategory, product, and English translation rows.

- [ ] **Step 3: Run seed tests and fix count mismatches**

Run:

```bash
cd backend/app
uv run pytest tests/test_dev_seed.py tests/test_local_reset.py -q
```

Expected: pass.

- [ ] **Step 4: Run the local reset script**

Run:

```bash
./scripts/reset_local_state.sh
```

Expected: `Verified counts:` includes the new tables and ends with `Local state reset complete.`

- [ ] **Step 5: Commit seed updates**

Run:

```bash
git add backend/app/src/app/db/dev_seed.py backend/app/scripts/seed_database.py backend/app/tests/test_dev_seed.py backend/app/tests/test_local_reset.py
git commit -m "feat(schema): seed reset baseline data"
```

## Task 8: Update Frontend Wire Type Comments

**Files:**
- Modify: `frontend/src/types/index.ts`
- Test: `frontend` TypeScript build through `npm run build`

- [ ] **Step 1: Update the file header**

Replace the header comment in `frontend/src/types/index.ts` with:

```typescript
/**
 * Khana Bazaar API wire types.
 *
 * These interfaces match the public FastAPI response/request shapes used by
 * the frontend. They are intentionally not exact database table models because
 * the backend composes compatibility fields such as full_name, seller_id,
 * category name, product name, and base_price from the reset baseline schema.
 */
```

- [ ] **Step 2: Run frontend lint and build**

Run:

```bash
cd frontend
npm run lint
npm run build
```

Expected: both commands exit 0.

- [ ] **Step 3: Commit frontend type comment**

Run:

```bash
git add frontend/src/types/index.ts
git commit -m "docs(frontend): clarify API wire types"
```

## Task 9: Full Verification

**Files:**
- No planned file changes.
- Test: backend and frontend quality gates.

- [ ] **Step 1: Run backend lint**

Run:

```bash
cd backend/app
uv run ruff check .
```

Expected: exit 0.

- [ ] **Step 2: Run backend type check**

Run:

```bash
cd backend/app
uv run mypy .
```

Expected: exit 0.

- [ ] **Step 3: Run backend tests**

Run:

```bash
cd backend/app
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Run frontend lint**

Run:

```bash
cd frontend
npm run lint
```

Expected: exit 0.

- [ ] **Step 5: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: exit 0.

- [ ] **Step 6: Check final diff**

Run:

```bash
git status --short
git log --oneline --max-count=8
```

Expected: only `new_schema.sql` remains untracked unless the implementation intentionally adds it; recent commits match the task commits above.

## Self-Review Checklist

- Spec coverage:
  - Reset baseline migration: Task 3.
  - SQLModel table coverage: Task 2.
  - Address normalization: Tasks 2, 4, 5, 6, 7.
  - User/profile split: Tasks 2, 4, 5, 7.
  - Multilingual catalog: Tasks 2, 6, 7.
  - Future commerce tables: Task 2 and Task 3.
  - Seed refresh: Task 7.
  - Compatibility responses: Tasks 5, 6, 8.
  - Verification gates: Task 9.
- Naming consistency:
  - Database profile ownership uses `seller_profile_id`.
  - API store response keeps `seller_id`.
  - Address relationship names are `address` on `Store` and `business_address` on `SellerProfile`.
  - Product compatibility keeps `base_price`.
  - Seller compatibility keeps `business_category`.
