<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Bulk Inventory Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `/seller/inventory/bulk` page (spreadsheet editor + drill-down product picker) plus an upsert endpoint and an eligible-products endpoint. Enforce that sellers may only stock products in their admin-approved services on both the new bulk endpoint and the existing single-row endpoint.

**Architecture:** Single upsert endpoint resolves insert vs update by `(store_id, product_id)`. A shared `assert_products_in_seller_services()` validator runs from both bulk and single-row endpoints. Frontend pre-validates rows; server runs all-or-nothing transaction. Translation helpers extracted to a shared module so the new endpoint reuses the same localization path as the catalog API.

**Tech Stack:** FastAPI 0.135, SQLModel 0.0.37 (asyncpg), Pytest + httpx for backend tests; Next.js 16 App Router, React 19, TypeScript 5, CSS Modules.

**Spec:** `docs/superpowers/specs/2026-05-05-bulk-inventory-design.md`

---

## File Structure

### Backend (new)
- `backend/app/src/app/services/catalog_translations.py` — public translation helpers extracted from `api/catalog.py`
- `backend/app/src/app/services/eligible_products.py` — query for products in seller's approved services
- `backend/app/src/app/schemas/inventory.py` — `BulkInventoryItem`, `BulkInventoryRequest`, `BulkInventoryError`, `EligibleProduct`
- `backend/app/src/app/db/scripts/__init__.py` — package init for one-shot scripts
- `backend/app/src/app/db/scripts/audit_inventory_service_membership.py` — operator-run audit
- `backend/app/tests/test_inventory_bulk.py` — bulk endpoint tests
- `backend/app/tests/test_eligible_products.py` — eligible-products endpoint tests

### Backend (modified)
- `backend/app/src/app/services/inventory.py` — add `assert_products_in_seller_services`, `bulk_upsert_inventory`
- `backend/app/src/app/api/catalog.py` — replace inline translation helpers with imports from `services/catalog_translations.py`
- `backend/app/src/app/api/sellers.py` — add `GET /me/eligible-products`
- `backend/app/src/app/api/stores.py` — add `PUT /{store_id}/inventory/bulk`; retrofit `POST /inventory` with service-membership check

### Frontend (new)
- `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx` — page shell, fetch, save handler
- `frontend/src/app/(operator)/seller/inventory/bulk/BulkInventorySheet.tsx` — editable table
- `frontend/src/app/(operator)/seller/inventory/bulk/EligibleProductPicker.tsx` — drill-down picker
- `frontend/src/app/(operator)/seller/inventory/bulk/BulkFillToolbar.tsx` — set-price/stock/% actions
- `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css` — page styles

### Frontend (modified)
- `frontend/src/types/index.ts` — add `EligibleProduct`, `BulkInventoryItem`, `BulkInventoryError`
- `frontend/src/app/(operator)/seller/inventory/page.tsx` — add "Bulk edit" link in toolbar

### Docs (modified)
- `docs/flows.md` — add inventory bulk-edit flow

---

## Task 1: Extract translation helpers to a shared module

**Why:** The new `/sellers/me/eligible-products` endpoint needs to localize four entity names. The helpers currently live as private functions inside `api/catalog.py`. Move them to a shared service module with public names so both routers can call them without import gymnastics.

**Files:**
- Create: `backend/app/src/app/services/catalog_translations.py`
- Modify: `backend/app/src/app/api/catalog.py` (replace inline helpers with imports)

- [ ] **Step 1: Create the new service module**

Write `backend/app/src/app/services/catalog_translations.py`:

```python
"""Localized translation lookups for catalog entities.

All helpers fall back to English when a translation is missing for the
requested language code, matching the behavior previously inlined in
api/catalog.py.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import (
    CategoryTranslation,
    LanguageCode,
    MasterProductTranslation,
    ServiceTranslation,
    SubcategoryTranslation,
)

_EN = LanguageCode.English.value


async def localized_service_translation(
    session: AsyncSession, service_id: int, lang: str
) -> ServiceTranslation | None:
    if lang != _EN:
        result = await session.exec(
            select(ServiceTranslation).where(
                ServiceTranslation.service_id == service_id,
                ServiceTranslation.language_code == lang,
            )
        )
        row = result.first()
        if row is not None:
            return row
    result = await session.exec(
        select(ServiceTranslation).where(
            ServiceTranslation.service_id == service_id,
            ServiceTranslation.language_code == _EN,
        )
    )
    return result.first()


async def localized_category_translation(
    session: AsyncSession, category_id: int, lang: str
) -> CategoryTranslation | None:
    if lang != _EN:
        result = await session.exec(
            select(CategoryTranslation).where(
                CategoryTranslation.category_id == category_id,
                CategoryTranslation.language_code == lang,
            )
        )
        row = result.first()
        if row is not None:
            return row
    result = await session.exec(
        select(CategoryTranslation).where(
            CategoryTranslation.category_id == category_id,
            CategoryTranslation.language_code == _EN,
        )
    )
    return result.first()


async def localized_subcategory_translation(
    session: AsyncSession, subcategory_id: int, lang: str
) -> SubcategoryTranslation | None:
    if lang != _EN:
        result = await session.exec(
            select(SubcategoryTranslation).where(
                SubcategoryTranslation.subcategory_id == subcategory_id,
                SubcategoryTranslation.language_code == lang,
            )
        )
        row = result.first()
        if row is not None:
            return row
    result = await session.exec(
        select(SubcategoryTranslation).where(
            SubcategoryTranslation.subcategory_id == subcategory_id,
            SubcategoryTranslation.language_code == _EN,
        )
    )
    return result.first()


async def localized_product_translation(
    session: AsyncSession, product_id: int, lang: str
) -> MasterProductTranslation | None:
    if lang != _EN:
        result = await session.exec(
            select(MasterProductTranslation).where(
                MasterProductTranslation.master_product_id == product_id,
                MasterProductTranslation.language_code == lang,
            )
        )
        row = result.first()
        if row is not None:
            return row
    result = await session.exec(
        select(MasterProductTranslation).where(
            MasterProductTranslation.master_product_id == product_id,
            MasterProductTranslation.language_code == _EN,
        )
    )
    return result.first()
```

- [ ] **Step 2: Replace the inline helpers in `api/catalog.py` with imports**

In `backend/app/src/app/api/catalog.py`:

1. Add this import near the other `from app.services.*` imports (or create the import line if none exists):

```python
from app.services.catalog_translations import (
    localized_category_translation as _localized_category_translation,
    localized_product_translation as _localized_product_translation,
    localized_service_translation as _localized_service_translation,
    localized_subcategory_translation as _localized_subcategory_translation,
)
```

2. Delete the four inline `async def _localized_*_translation` function bodies (lines 137-224 in the current file). Leave existing call sites alone — they still reference the same private names due to the `as _localized_*` aliases.

- [ ] **Step 3: Run the existing catalog tests to confirm nothing broke**

```bash
cd backend/app
uv run pytest tests/test_catalog.py -v
```

Expected: all existing tests PASS.

- [ ] **Step 4: Run lint + types**

```bash
uv run ruff check .
uv run mypy .
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/services/catalog_translations.py backend/app/src/app/api/catalog.py
git commit -m "refactor(catalog): extract localized translation helpers to shared service"
```

---

## Task 2: Add the `assert_products_in_seller_services` helper (TDD)

**Files:**
- Modify: `backend/app/src/app/services/inventory.py`
- Test: `backend/app/tests/test_inventory_bulk.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_inventory_bulk.py`:

```python
from typing import Any, AsyncGenerator, Iterator

import pytest
from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_seller, get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    LanguageCode,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
)
from app.models.profile import (
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from app.services.inventory import assert_products_in_seller_services
from tests._helpers import make_address

mock_seller = User(id=2, email="seller@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture
async def seeded(session: AsyncSession) -> AsyncGenerator[dict[str, Any], None]:
    """Seed: seller approved for Grocery only; 1 grocery product, 1 pharmacy product."""
    session.add(User(**mock_seller.model_dump()))
    await session.flush()

    address = Address(**make_address())
    session.add(address)
    await session.flush()

    profile = SellerProfile(
        user_id=mock_seller.id,
        first_name="S",
        business_name="S Store",
        phone="+919811110000",
        gst_number="06AAAAA1111A1Z1",
        fssai_license="44556677889900",
        bank_account_number="80100200300700",
        bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=address.id,
    )
    session.add(profile)
    await session.flush()

    grocery = Service(slug="grocery")
    pharmacy = Service(slug="pharmacy")
    session.add_all([grocery, pharmacy])
    await session.flush()
    session.add_all([
        ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"),
        ServiceTranslation(service_id=pharmacy.id, language_code="en", name="Pharmacy"),
        SellerProfileService(seller_profile_id=profile.id, service_id=grocery.id),
    ])

    grocery_cat = Category(slug="staples", service_id=grocery.id)
    pharmacy_cat = Category(slug="otc", service_id=pharmacy.id)
    session.add_all([grocery_cat, pharmacy_cat])
    await session.flush()

    grocery_sub = Subcategory(slug="atta", category_id=grocery_cat.id)
    pharmacy_sub = Subcategory(slug="painkillers", category_id=pharmacy_cat.id)
    session.add_all([grocery_sub, pharmacy_sub])
    await session.flush()

    atta = MasterProduct(subcategory_id=grocery_sub.id, base_price=280.0)
    paracetamol = MasterProduct(subcategory_id=pharmacy_sub.id, base_price=20.0)
    session.add_all([atta, paracetamol])
    await session.flush()
    session.add_all([
        MasterProductTranslation(master_product_id=atta.id, language_code="en", name="Aashirvaad Atta 5kg"),
        MasterProductTranslation(master_product_id=paracetamol.id, language_code="en", name="Paracetamol 500mg"),
    ])

    store_address = Address(**make_address())
    session.add(store_address)
    await session.flush()
    store = Store(name="S Store", seller_profile_id=profile.id, address_id=store_address.id)
    session.add(store)
    await session.commit()

    yield {
        "profile_id": profile.id,
        "store_id": store.id,
        "grocery_product_id": atta.id,
        "pharmacy_product_id": paracetamol.id,
    }


@pytest.fixture
def override_as_seller() -> Iterator[None]:
    app.dependency_overrides[get_current_seller] = lambda: mock_seller
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    yield
    app.dependency_overrides.pop(get_current_seller, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_assert_products_passes_for_approved_service(
    session: AsyncSession, seeded: dict[str, Any]
) -> None:
    # Should not raise.
    await assert_products_in_seller_services(
        session, seeded["profile_id"], [seeded["grocery_product_id"]]
    )


@pytest.mark.asyncio
async def test_assert_products_rejects_unapproved_service(
    session: AsyncSession, seeded: dict[str, Any]
) -> None:
    with pytest.raises(HTTPException) as exc:
        await assert_products_in_seller_services(
            session,
            seeded["profile_id"],
            [seeded["grocery_product_id"], seeded["pharmacy_product_id"]],
        )
    assert exc.value.status_code == 403
    assert "SERVICE_NOT_APPROVED" in str(exc.value.detail)
```

- [ ] **Step 2: Run the failing test**

```bash
cd backend/app
uv run pytest tests/test_inventory_bulk.py::test_assert_products_passes_for_approved_service tests/test_inventory_bulk.py::test_assert_products_rejects_unapproved_service -v
```

Expected: FAIL with `ImportError: cannot import name 'assert_products_in_seller_services' from 'app.services.inventory'`.

- [ ] **Step 3: Implement the helper**

Append to `backend/app/src/app/services/inventory.py`:

```python
from typing import Iterable

from fastapi import HTTPException
from sqlmodel import select

from app.models.catalog import Category, MasterProduct, Subcategory
from app.models.profile import SellerProfileService


async def assert_products_in_seller_services(
    session: AsyncSession,
    seller_profile_id: int,
    product_ids: Iterable[int],
) -> None:
    """Raise 403 SERVICE_NOT_APPROVED if any product belongs to a service
    not in the seller's approved set."""
    ids = list({pid for pid in product_ids})
    if not ids:
        return

    # Approved service ids for this seller
    approved_result = await session.exec(
        select(SellerProfileService.service_id).where(
            SellerProfileService.seller_profile_id == seller_profile_id
        )
    )
    approved = set(approved_result.all())

    # Service id for each product (via subcategory → category → service)
    stmt = (
        select(MasterProduct.id, Category.service_id)
        .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
        .join(Category, Category.id == Subcategory.category_id)  # type: ignore[arg-type]
        .where(MasterProduct.id.in_(ids))  # type: ignore[union-attr]
    )
    rows = await session.exec(stmt)
    by_product = {pid: sid for pid, sid in rows.all()}

    missing = [pid for pid in ids if pid not in by_product]
    if missing:
        raise HTTPException(
            status_code=404,
            detail={"code": "PRODUCT_NOT_FOUND", "product_ids": missing},
        )

    forbidden = [pid for pid, sid in by_product.items() if sid not in approved]
    if forbidden:
        raise HTTPException(
            status_code=403,
            detail={"code": "SERVICE_NOT_APPROVED", "product_ids": forbidden},
        )
```

Note: the `from typing import Iterable` import already exists at the top of the file — do not duplicate. Add only `from fastapi import HTTPException`, the new model imports, and the function.

- [ ] **Step 4: Run the tests, confirm pass**

```bash
uv run pytest tests/test_inventory_bulk.py::test_assert_products_passes_for_approved_service tests/test_inventory_bulk.py::test_assert_products_rejects_unapproved_service -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/services/inventory.py backend/app/tests/test_inventory_bulk.py
git commit -m "feat(inventory): add assert_products_in_seller_services validator"
```

---

## Task 3: Add the `bulk_upsert_inventory` service helper (TDD)

**Files:**
- Modify: `backend/app/src/app/services/inventory.py`
- Modify: `backend/app/tests/test_inventory_bulk.py`
- Create: `backend/app/src/app/schemas/inventory.py`

- [ ] **Step 1: Create the request/response schemas**

Write `backend/app/src/app/schemas/inventory.py`:

```python
"""Wire schemas for inventory bulk endpoints."""

from typing import Literal

from pydantic import BaseModel, Field

BulkErrorCode = Literal[
    "PRICE_INVALID",
    "STOCK_INVALID",
    "PRODUCT_NOT_FOUND",
    "SERVICE_NOT_APPROVED",
    "DUPLICATE_PRODUCT",
    "ROW_LIMIT",
]


class BulkInventoryItem(BaseModel):
    """One row of a bulk upsert payload.

    No `inventory_id` field — the server resolves insert vs update by
    looking up `(store_id, product_id)`.
    """

    product_id: int
    price: float
    stock: int
    is_available: bool = True


class BulkInventoryRequest(BaseModel):
    items: list[BulkInventoryItem] = Field(default_factory=list)


class BulkInventoryError(BaseModel):
    index: int
    product_id: int
    code: BulkErrorCode
    message: str


class EligibleProduct(BaseModel):
    id: int
    name: str
    base_price: float
    subcategory_id: int
    subcategory_name: str
    category_id: int
    category_name: str
    service_id: int
    service_name: str
    in_inventory: bool  # True iff a storeinventory row exists for this product in the seller's store
```

- [ ] **Step 2: Write the failing test for bulk_upsert_inventory**

Append to `backend/app/tests/test_inventory_bulk.py`:

```python
from app.schemas.inventory import BulkInventoryItem
from app.services.inventory import bulk_upsert_inventory


@pytest.mark.asyncio
async def test_bulk_upsert_creates_and_updates_in_one_call(
    session: AsyncSession, seeded: dict[str, Any]
) -> None:
    # Pre-existing row for the grocery product.
    existing = StoreInventory(
        store_id=seeded["store_id"],
        product_id=seeded["grocery_product_id"],
        price=200.0,
        stock=5,
        is_available=True,
    )
    session.add(existing)
    await session.commit()

    # Add a second grocery product to give us a fresh insert candidate.
    second_grocery = MasterProduct(subcategory_id=existing.product_id and 0, base_price=0.0)
    # Re-fetch the subcategory used by the existing grocery product so we share it.
    existing_product = await session.get(MasterProduct, seeded["grocery_product_id"])
    assert existing_product is not None
    second_grocery = MasterProduct(
        subcategory_id=existing_product.subcategory_id, base_price=50.0
    )
    session.add(second_grocery)
    await session.flush()
    session.add(MasterProductTranslation(
        master_product_id=second_grocery.id, language_code="en", name="Tata Salt 1kg"
    ))
    await session.commit()

    items = [
        BulkInventoryItem(product_id=seeded["grocery_product_id"], price=275.0, stock=50, is_available=True),
        BulkInventoryItem(product_id=second_grocery.id, price=22.0, stock=120, is_available=True),
    ]

    rows = await bulk_upsert_inventory(session, seeded["store_id"], items)
    await session.commit()

    assert len(rows) == 2
    by_product = {r.product_id: r for r in rows}
    assert by_product[seeded["grocery_product_id"]].price == 275.0
    assert by_product[seeded["grocery_product_id"]].stock == 50
    assert by_product[second_grocery.id].price == 22.0
    assert by_product[second_grocery.id].stock == 120
    # The existing row was updated, not duplicated:
    db_rows = await session.exec(
        select(StoreInventory).where(StoreInventory.store_id == seeded["store_id"])
    )
    assert len(list(db_rows.all())) == 2


@pytest.mark.asyncio
async def test_bulk_upsert_dedup_last_wins(
    session: AsyncSession, seeded: dict[str, Any]
) -> None:
    items = [
        BulkInventoryItem(product_id=seeded["grocery_product_id"], price=100.0, stock=10),
        BulkInventoryItem(product_id=seeded["grocery_product_id"], price=200.0, stock=20),
    ]
    rows = await bulk_upsert_inventory(session, seeded["store_id"], items)
    await session.commit()

    assert len(rows) == 1
    assert rows[0].price == 200.0
    assert rows[0].stock == 20
```

- [ ] **Step 3: Run failing tests**

```bash
uv run pytest tests/test_inventory_bulk.py::test_bulk_upsert_creates_and_updates_in_one_call tests/test_inventory_bulk.py::test_bulk_upsert_dedup_last_wins -v
```

Expected: FAIL with `ImportError: cannot import name 'bulk_upsert_inventory'`.

- [ ] **Step 4: Implement `bulk_upsert_inventory`**

Append to `backend/app/src/app/services/inventory.py`:

```python
from app.schemas.inventory import BulkInventoryItem


async def bulk_upsert_inventory(
    session: AsyncSession,
    store_id: int,
    items: list[BulkInventoryItem],
) -> list[StoreInventory]:
    """Insert new rows and update existing ones in a single transaction.

    Dedup by product_id (last write wins). Caller commits.
    Caller is responsible for service-membership and field validation
    BEFORE calling this — the service layer trusts its inputs.
    """
    if not items:
        return []

    # Dedup, preserving the LAST occurrence per product_id.
    deduped: dict[int, BulkInventoryItem] = {}
    for item in items:
        deduped[item.product_id] = item
    payload = list(deduped.values())

    product_ids = [it.product_id for it in payload]

    existing_stmt = select(StoreInventory).where(
        StoreInventory.store_id == store_id,
        StoreInventory.product_id.in_(product_ids),  # type: ignore[union-attr]
    )
    existing_rows = list((await session.exec(existing_stmt)).all())
    existing_ids = sorted([row.id for row in existing_rows if row.id is not None])

    # Lock existing rows in deterministic id order to avoid checkout deadlocks.
    locked = await lock_inventory_rows(session, existing_ids)
    locked_by_product = {row.product_id: row for row in locked}

    out: list[StoreInventory] = []
    for item in payload:
        existing = locked_by_product.get(item.product_id)
        if existing is not None:
            existing.price = item.price
            existing.stock = item.stock
            existing.is_available = item.is_available
            session.add(existing)
            out.append(existing)
        else:
            new_row = StoreInventory(
                store_id=store_id,
                product_id=item.product_id,
                price=item.price,
                stock=item.stock,
                is_available=item.is_available,
            )
            session.add(new_row)
            out.append(new_row)

    await session.flush()
    return out
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
uv run pytest tests/test_inventory_bulk.py -v
```

Expected: all tests in this file PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/services/inventory.py backend/app/src/app/schemas/inventory.py backend/app/tests/test_inventory_bulk.py
git commit -m "feat(inventory): add bulk_upsert_inventory service and request schemas"
```

---

## Task 4: Add the eligible-products query helper (TDD)

**Files:**
- Create: `backend/app/src/app/services/eligible_products.py`
- Test: `backend/app/tests/test_eligible_products.py`

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_eligible_products.py`:

```python
from typing import Any, AsyncGenerator

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
    CategoryTranslation,
)
from app.models.profile import (
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from app.services.eligible_products import list_eligible_products
from tests._helpers import make_address


@pytest.fixture
async def fixt(session: AsyncSession) -> AsyncGenerator[dict[str, Any], None]:
    """Seller approved for Grocery only. Two grocery products (one already in inventory),
    one pharmacy product."""
    user = User(email="seller@kb.com", role=UserRole.Seller, is_active=True)
    session.add(user)
    await session.flush()

    addr = Address(**make_address())
    session.add(addr)
    await session.flush()

    profile = SellerProfile(
        user_id=user.id,
        first_name="S",
        business_name="S Store",
        phone="+919811110000",
        gst_number="06AAAAA1111A1Z1",
        fssai_license="44556677889900",
        bank_account_number="80100200300700",
        bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(profile)
    await session.flush()

    grocery = Service(slug="grocery")
    pharmacy = Service(slug="pharmacy")
    session.add_all([grocery, pharmacy])
    await session.flush()
    session.add_all([
        ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"),
        ServiceTranslation(service_id=pharmacy.id, language_code="en", name="Pharmacy"),
        SellerProfileService(seller_profile_id=profile.id, service_id=grocery.id),
    ])

    cat_g = Category(slug="staples", service_id=grocery.id)
    cat_p = Category(slug="otc", service_id=pharmacy.id)
    session.add_all([cat_g, cat_p])
    await session.flush()
    session.add_all([
        CategoryTranslation(category_id=cat_g.id, language_code="en", name="Staples"),
        CategoryTranslation(category_id=cat_p.id, language_code="en", name="OTC"),
    ])

    sub_g = Subcategory(slug="atta", category_id=cat_g.id)
    sub_p = Subcategory(slug="pain", category_id=cat_p.id)
    session.add_all([sub_g, sub_p])
    await session.flush()
    session.add_all([
        SubcategoryTranslation(subcategory_id=sub_g.id, language_code="en", name="Atta"),
        SubcategoryTranslation(subcategory_id=sub_p.id, language_code="en", name="Painkillers"),
    ])

    atta = MasterProduct(subcategory_id=sub_g.id, base_price=280.0)
    salt = MasterProduct(subcategory_id=sub_g.id, base_price=22.0)
    paracetamol = MasterProduct(subcategory_id=sub_p.id, base_price=20.0)
    session.add_all([atta, salt, paracetamol])
    await session.flush()
    session.add_all([
        MasterProductTranslation(master_product_id=atta.id, language_code="en", name="Aashirvaad Atta 5kg"),
        MasterProductTranslation(master_product_id=salt.id, language_code="en", name="Tata Salt 1kg"),
        MasterProductTranslation(master_product_id=paracetamol.id, language_code="en", name="Paracetamol 500mg"),
    ])

    store_addr = Address(**make_address())
    session.add(store_addr)
    await session.flush()
    store = Store(name="S Store", seller_profile_id=profile.id, address_id=store_addr.id)
    session.add(store)
    await session.flush()
    session.add(StoreInventory(store_id=store.id, product_id=atta.id, price=275.0, stock=10))
    await session.commit()

    yield {
        "profile_id": profile.id,
        "store_id": store.id,
        "atta_id": atta.id,
        "salt_id": salt.id,
        "paracetamol_id": paracetamol.id,
    }


@pytest.mark.asyncio
async def test_list_eligible_filters_unapproved_services(
    session: AsyncSession, fixt: dict[str, Any]
) -> None:
    rows = await list_eligible_products(
        session, profile_id=fixt["profile_id"], store_id=fixt["store_id"], lang="en"
    )
    ids = {r.id for r in rows}
    assert fixt["atta_id"] in ids
    assert fixt["salt_id"] in ids
    assert fixt["paracetamol_id"] not in ids


@pytest.mark.asyncio
async def test_list_eligible_marks_in_inventory(
    session: AsyncSession, fixt: dict[str, Any]
) -> None:
    rows = await list_eligible_products(
        session, profile_id=fixt["profile_id"], store_id=fixt["store_id"], lang="en"
    )
    by_id = {r.id: r for r in rows}
    assert by_id[fixt["atta_id"]].in_inventory is True
    assert by_id[fixt["salt_id"]].in_inventory is False
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_eligible_products.py -v
```

Expected: FAIL with `ImportError: cannot import name 'list_eligible_products'`.

- [ ] **Step 3: Implement the helper**

Create `backend/app/src/app/services/eligible_products.py`:

```python
"""Query products that a seller is allowed to add to their store
(filtered by their approved services), with localized names and an
already-in-inventory flag."""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Category, MasterProduct, Subcategory
from app.models.profile import SellerProfileService
from app.models.store import StoreInventory
from app.schemas.inventory import EligibleProduct
from app.services.catalog_translations import (
    localized_category_translation,
    localized_product_translation,
    localized_service_translation,
    localized_subcategory_translation,
)


async def list_eligible_products(
    session: AsyncSession,
    profile_id: int,
    store_id: int,
    lang: str,
) -> list[EligibleProduct]:
    # Approved service ids
    svc_result = await session.exec(
        select(SellerProfileService.service_id).where(
            SellerProfileService.seller_profile_id == profile_id
        )
    )
    approved_service_ids = list(svc_result.all())
    if not approved_service_ids:
        return []

    # Products joined to subcategory + category, filtered by approved services
    stmt = (
        select(MasterProduct, Subcategory, Category)
        .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
        .join(Category, Category.id == Subcategory.category_id)  # type: ignore[arg-type]
        .where(Category.service_id.in_(approved_service_ids))  # type: ignore[union-attr]
    )
    rows = list((await session.exec(stmt)).all())
    if not rows:
        return []

    # Inventory presence for this store
    product_ids = [p.id for p, _s, _c in rows if p.id is not None]
    inv_result = await session.exec(
        select(StoreInventory.product_id).where(
            StoreInventory.store_id == store_id,
            StoreInventory.product_id.in_(product_ids),  # type: ignore[union-attr]
        )
    )
    in_inventory_ids = set(inv_result.all())

    out: list[EligibleProduct] = []
    for product, subcategory, category in rows:
        assert product.id is not None and subcategory.id is not None and category.id is not None
        prod_t = await localized_product_translation(session, product.id, lang)
        sub_t = await localized_subcategory_translation(session, subcategory.id, lang)
        cat_t = await localized_category_translation(session, category.id, lang)
        svc_t = await localized_service_translation(session, category.service_id, lang)

        out.append(EligibleProduct(
            id=product.id,
            name=prod_t.name if prod_t else f"product-{product.id}",
            base_price=product.base_price,
            subcategory_id=subcategory.id,
            subcategory_name=sub_t.name if sub_t else subcategory.slug,
            category_id=category.id,
            category_name=cat_t.name if cat_t else category.slug,
            service_id=category.service_id,
            service_name=svc_t.name if svc_t else f"service-{category.service_id}",
            in_inventory=product.id in in_inventory_ids,
        ))
    return out
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_eligible_products.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/services/eligible_products.py backend/app/tests/test_eligible_products.py
git commit -m "feat(inventory): add list_eligible_products query helper"
```

---

## Task 5: Wire `GET /api/v1/sellers/me/eligible-products` (TDD)

**Files:**
- Modify: `backend/app/src/app/api/sellers.py`
- Modify: `backend/app/tests/test_eligible_products.py`

- [ ] **Step 1: Add an endpoint test**

Append to `backend/app/tests/test_eligible_products.py`:

```python
from typing import Iterator

from httpx import ASGITransport, AsyncClient

from app import app
from app.core.security import get_current_seller, get_current_user


@pytest.fixture
def override_as_user(fixt: dict[str, Any]) -> Iterator[None]:
    user = User(id=1, email="seller@kb.com", role=UserRole.Seller, is_active=True)
    app.dependency_overrides[get_current_seller] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.pop(get_current_seller, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_eligible_products_endpoint_returns_filtered_list(
    fixt: dict[str, Any], override_as_user: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/me/eligible-products")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = {p["id"] for p in body}
        assert fixt["atta_id"] in ids
        assert fixt["salt_id"] in ids
        assert fixt["paracetamol_id"] not in ids
```

Note: `User(id=1, …)` matches the User row created in the `fixt` fixture only if the autoincrement starts at 1 in the test DB. The test DB is dropped/recreated per function (per `conftest.py`), so id=1 is the first user. This pattern matches `test_stores.py`.

- [ ] **Step 2: Run failing test**

```bash
uv run pytest tests/test_eligible_products.py::test_eligible_products_endpoint_returns_filtered_list -v
```

Expected: FAIL with 404 (endpoint not registered yet).

- [ ] **Step 3: Add the endpoint**

In `backend/app/src/app/api/sellers.py`, add:

```python
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.locale import get_request_locale
from app.core.security import get_current_seller
from app.db.session import get_db_session
from app.models.base import User
from app.models.profile import SellerProfile
from app.models.store import Store
from app.schemas.inventory import EligibleProduct
from app.services.eligible_products import list_eligible_products


@router.get("/me/eligible-products", response_model=List[EligibleProduct])
async def list_my_eligible_products(
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
    lang: str = Depends(get_request_locale),
) -> List[EligibleProduct]:
    profile_result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == seller.id)
    )
    profile = profile_result.first()
    if profile is None or profile.id is None:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    store_result = await session.exec(
        select(Store).where(Store.seller_profile_id == profile.id)
    )
    store = store_result.first()
    if store is None or store.id is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "STORE_NOT_PROVISIONED", "message": "No store yet"},
        )

    return await list_eligible_products(
        session, profile_id=profile.id, store_id=store.id, lang=lang
    )
```

If imports above are already partly present in `sellers.py`, dedupe them — do not duplicate.

- [ ] **Step 4: Run, confirm pass**

```bash
uv run pytest tests/test_eligible_products.py -v
uv run ruff check . && uv run mypy .
```

Expected: all PASS, lint clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/sellers.py backend/app/tests/test_eligible_products.py
git commit -m "feat(api): add GET /sellers/me/eligible-products endpoint"
```

---

## Task 6: Wire `PUT /api/v1/stores/{store_id}/inventory/bulk` (TDD)

**Files:**
- Modify: `backend/app/src/app/api/stores.py`
- Modify: `backend/app/tests/test_inventory_bulk.py`

- [ ] **Step 1: Write endpoint tests**

Append to `backend/app/tests/test_inventory_bulk.py`:

```python
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_bulk_endpoint_creates_and_updates_atomically(
    seeded: dict[str, Any], override_as_seller: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "items": [
                {"product_id": seeded["grocery_product_id"], "price": 275.0, "stock": 50, "is_available": True},
            ]
        }
        resp = await ac.put(
            f"/api/v1/stores/{seeded['store_id']}/inventory/bulk", json=payload
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body) == 1
        assert body[0]["price"] == 275.0
        assert body[0]["stock"] == 50


@pytest.mark.asyncio
async def test_bulk_endpoint_rejects_unapproved_service(
    seeded: dict[str, Any], override_as_seller: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "items": [
                {"product_id": seeded["pharmacy_product_id"], "price": 20.0, "stock": 5, "is_available": True},
            ]
        }
        resp = await ac.put(
            f"/api/v1/stores/{seeded['store_id']}/inventory/bulk", json=payload
        )
        assert resp.status_code == 403, resp.text
        assert "SERVICE_NOT_APPROVED" in resp.text


@pytest.mark.asyncio
async def test_bulk_endpoint_caps_at_200_rows(
    seeded: dict[str, Any], override_as_seller: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        items = [
            {"product_id": seeded["grocery_product_id"], "price": 1.0, "stock": 1, "is_available": True}
            for _ in range(201)
        ]
        resp = await ac.put(
            f"/api/v1/stores/{seeded['store_id']}/inventory/bulk", json={"items": items}
        )
        assert resp.status_code == 422, resp.text
        assert "ROW_LIMIT" in resp.text


@pytest.mark.asyncio
async def test_bulk_endpoint_rejects_invalid_price(
    seeded: dict[str, Any], override_as_seller: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "items": [
                {"product_id": seeded["grocery_product_id"], "price": 0.0, "stock": 5, "is_available": True},
            ]
        }
        resp = await ac.put(
            f"/api/v1/stores/{seeded['store_id']}/inventory/bulk", json=payload
        )
        assert resp.status_code == 422, resp.text
        assert "PRICE_INVALID" in resp.text


@pytest.mark.asyncio
async def test_bulk_endpoint_rolls_back_on_invalid_row(
    session: AsyncSession,
    seeded: dict[str, Any],
    override_as_seller: None,
) -> None:
    """One invalid row → entire batch rejected, DB unchanged."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "items": [
                {"product_id": seeded["grocery_product_id"], "price": 99.0, "stock": 9, "is_available": True},
                {"product_id": seeded["pharmacy_product_id"], "price": 99.0, "stock": 9, "is_available": True},  # forbidden
            ]
        }
        resp = await ac.put(
            f"/api/v1/stores/{seeded['store_id']}/inventory/bulk", json=payload
        )
        assert resp.status_code == 403

    rows = list((await session.exec(
        select(StoreInventory).where(StoreInventory.store_id == seeded["store_id"])
    )).all())
    assert rows == []
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_inventory_bulk.py -v -k "bulk_endpoint"
```

Expected: all the new bulk_endpoint tests FAIL with 404 / 405.

- [ ] **Step 3: Implement the endpoint**

In `backend/app/src/app/api/stores.py`, after the existing `delete_inventory` endpoint, add:

```python
from app.schemas.inventory import (
    BulkInventoryError,
    BulkInventoryItem,
    BulkInventoryRequest,
)
from app.services.inventory import (
    assert_products_in_seller_services,
    bulk_upsert_inventory,
)

_BULK_ROW_LIMIT = 200


def _validate_bulk_items(items: list[BulkInventoryItem]) -> list[BulkInventoryError]:
    errs: list[BulkInventoryError] = []
    seen: set[int] = set()
    for idx, item in enumerate(items):
        if item.price <= 0 or item.price > 999_999:
            errs.append(BulkInventoryError(
                index=idx, product_id=item.product_id,
                code="PRICE_INVALID", message="Price must be > 0 and <= 999999",
            ))
        if item.stock < 0:
            errs.append(BulkInventoryError(
                index=idx, product_id=item.product_id,
                code="STOCK_INVALID", message="Stock must be >= 0",
            ))
        if item.product_id in seen:
            errs.append(BulkInventoryError(
                index=idx, product_id=item.product_id,
                code="DUPLICATE_PRODUCT", message="Product appears more than once",
            ))
        seen.add(item.product_id)
    return errs


@router.put("/{store_id}/inventory/bulk", response_model=List[StoreInventory])
async def bulk_upsert_store_inventory(
    store_id: int,
    payload: BulkInventoryRequest,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> List[StoreInventory]:
    store = await _authorize_store_ownership(session, store_id, seller, allow_admin=False)

    if len(payload.items) > _BULK_ROW_LIMIT:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ROW_LIMIT",
                "message": f"At most {_BULK_ROW_LIMIT} items per request",
            },
        )

    field_errors = _validate_bulk_items(payload.items)
    if field_errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": [e.model_dump() for e in field_errors]},
        )

    profile_id = store.seller_profile_id
    product_ids = [it.product_id for it in payload.items]
    await assert_products_in_seller_services(session, profile_id, product_ids)

    rows = await bulk_upsert_inventory(session, store_id, payload.items)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return rows
```

- [ ] **Step 4: Run all bulk tests, confirm pass**

```bash
uv run pytest tests/test_inventory_bulk.py -v
uv run ruff check . && uv run mypy .
```

Expected: all PASS, lint clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/stores.py backend/app/tests/test_inventory_bulk.py
git commit -m "feat(api): add PUT /stores/{id}/inventory/bulk upsert endpoint"
```

---

## Task 7: Retrofit single-row `POST /inventory` with the service-membership check

**Files:**
- Modify: `backend/app/src/app/api/stores.py`
- Modify: `backend/app/tests/test_inventory_bulk.py`

- [ ] **Step 1: Write the failing regression test**

Append to `backend/app/tests/test_inventory_bulk.py`:

```python
@pytest.mark.asyncio
async def test_single_post_inventory_now_enforces_service_membership(
    seeded: dict[str, Any], override_as_seller: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Seller is approved for Grocery only; pharmacy product must be rejected.
        payload = {
            "product_id": seeded["pharmacy_product_id"],
            "price": 20.0,
            "stock": 5,
            "is_available": True,
            "store_id": seeded["store_id"],
        }
        resp = await ac.post(
            f"/api/v1/stores/{seeded['store_id']}/inventory", json=payload
        )
        assert resp.status_code == 403, resp.text
        assert "SERVICE_NOT_APPROVED" in resp.text
```

- [ ] **Step 2: Run failing test**

```bash
uv run pytest tests/test_inventory_bulk.py::test_single_post_inventory_now_enforces_service_membership -v
```

Expected: FAIL with status_code 200 (currently allowed).

- [ ] **Step 3: Patch `add_inventory` to call the validator**

In `backend/app/src/app/api/stores.py`, locate the `add_inventory` function (currently around lines 190-219). Replace it with:

```python
@router.post("/{store_id}/inventory", response_model=StoreInventory)
async def add_inventory(
    store_id: int,
    inventory: StoreInventory,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> StoreInventory:
    store = await _authorize_store_ownership(session, store_id, seller, allow_admin=False)

    product = await session.get(MasterProduct, inventory.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Master product not found")

    await assert_products_in_seller_services(
        session, store.seller_profile_id, [inventory.product_id]
    )

    check_stmt = select(StoreInventory).where(
        StoreInventory.store_id == store_id,
        StoreInventory.product_id == inventory.product_id,
    )
    existing = await session.exec(check_stmt)
    if existing.first():
        raise HTTPException(
            status_code=400,
            detail="Product already exists in store inventory. Use PUT to update.",
        )

    inventory.id = None
    inventory.store_id = store_id
    session.add(inventory)
    await session.commit()
    await session.refresh(inventory)
    return inventory
```

- [ ] **Step 4: Run regression + existing tests**

```bash
uv run pytest tests/test_inventory_bulk.py tests/test_stores.py -v
```

Expected: new test PASS; existing `test_stores.py` tests still PASS (none of them add unapproved-service products in the fixture).

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/stores.py backend/app/tests/test_inventory_bulk.py
git commit -m "fix(api): enforce service membership on POST /stores/{id}/inventory"
```

---

## Task 8: Add the audit script for grandfathered rows

**Files:**
- Create: `backend/app/src/app/db/scripts/__init__.py`
- Create: `backend/app/src/app/db/scripts/audit_inventory_service_membership.py`

- [ ] **Step 1: Create the package init**

Write `backend/app/src/app/db/scripts/__init__.py`:

```python
```

(Empty file — marks the directory as a Python package.)

- [ ] **Step 2: Write the audit script**

Write `backend/app/src/app/db/scripts/audit_inventory_service_membership.py`:

```python
"""One-shot audit: log any storeinventory rows whose product belongs to
a service NOT in the owning seller's approved services. Does not modify
data — purely a diagnostic for the bulk-inventory rollout (2026-05-05).

Run from `backend/app`:
    uv run python -m app.db.scripts.audit_inventory_service_membership
"""

import asyncio
import logging

from sqlmodel import select

from app.db.session import async_session_maker
from app.models.catalog import Category, MasterProduct, Subcategory
from app.models.profile import SellerProfile, SellerProfileService
from app.models.store import Store, StoreInventory

logger = logging.getLogger("audit_inventory_service_membership")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def audit() -> int:
    async with async_session_maker() as session:
        # All inventory rows joined to (store → profile, product → subcategory → category → service)
        stmt = (
            select(
                StoreInventory.id,
                StoreInventory.store_id,
                StoreInventory.product_id,
                Store.seller_profile_id,
                Category.service_id,
            )
            .join(Store, Store.id == StoreInventory.store_id)  # type: ignore[arg-type]
            .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
            .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
            .join(Category, Category.id == Subcategory.category_id)  # type: ignore[arg-type]
        )
        rows = list((await session.exec(stmt)).all())

        # Approved services per profile
        approved_stmt = select(
            SellerProfileService.seller_profile_id,
            SellerProfileService.service_id,
        )
        approved_pairs = list((await session.exec(approved_stmt)).all())
        approved_by_profile: dict[int, set[int]] = {}
        for profile_id, svc_id in approved_pairs:
            approved_by_profile.setdefault(profile_id, set()).add(svc_id)

        violations = 0
        for inv_id, store_id, product_id, profile_id, service_id in rows:
            approved = approved_by_profile.get(profile_id, set())
            if service_id not in approved:
                violations += 1
                logger.warning(
                    "violation: inventory_id=%s store_id=%s product_id=%s "
                    "profile_id=%s product_service_id=%s approved_services=%s",
                    inv_id, store_id, product_id, profile_id, service_id, sorted(approved),
                )
        logger.info("audit complete — %d violation(s) across %d rows", violations, len(rows))
        return violations


if __name__ == "__main__":
    asyncio.run(audit())
```

- [ ] **Step 3: Verify the script runs against the test DB**

```bash
cd backend/app
uv run python -m app.db.scripts.audit_inventory_service_membership 2>&1 | head -5
```

Expected: log line ending in `audit complete — 0 violation(s) across N rows` (where N depends on dev DB state). Non-zero violations are tolerated; the script never raises.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/db/scripts/__init__.py backend/app/src/app/db/scripts/audit_inventory_service_membership.py
git commit -m "chore(db): add one-shot audit script for inventory service membership"
```

---

## Task 9: Frontend types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add the new types**

Append to `frontend/src/types/index.ts`:

```ts
export interface EligibleProduct {
  id: number;
  name: string;
  base_price: number;
  subcategory_id: number;
  subcategory_name: string;
  category_id: number;
  category_name: string;
  service_id: number;
  service_name: string;
  in_inventory: boolean;
}

export interface BulkInventoryItem {
  product_id: number;
  price: number;
  stock: number;
  is_available: boolean;
}

export type BulkInventoryErrorCode =
  | "PRICE_INVALID"
  | "STOCK_INVALID"
  | "PRODUCT_NOT_FOUND"
  | "SERVICE_NOT_APPROVED"
  | "DUPLICATE_PRODUCT"
  | "ROW_LIMIT";

export interface BulkInventoryError {
  index: number;
  product_id: number;
  code: BulkInventoryErrorCode;
  message: string;
}
```

- [ ] **Step 2: Build to verify**

```bash
cd frontend
npm run lint
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add eligible product and bulk inventory types"
```

---

## Task 10: Bulk page shell + data fetch

**Files:**
- Create: `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`
- Create: `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css`

- [ ] **Step 1: Write the page skeleton**

Create `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import {
  BulkInventoryItem,
  EligibleProduct,
  Store,
  StoreInventory,
} from "@/types";

import styles from "./bulk.module.css";

export type SheetRow = {
  inventory_id: number | null;
  product_id: number;
  product_name: string;
  service_name: string;
  category_name: string;
  subcategory_name: string;
  price: string;
  stock: string;
  is_available: boolean;
  dirty: boolean;
  errors: Partial<Record<"price" | "stock", string>>;
};

export default function BulkInventoryPage() {
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();

  const [store, setStore] = useState<Store | null>(null);
  const [eligible, setEligible] = useState<EligibleProduct[]>([]);
  const [rows, setRows] = useState<SheetRow[]>([]);
  const [fetching, setFetching] = useState(true);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "seller")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!authLoading && dbUser && token) {
      Promise.all([
        get<Store[]>("/api/v1/stores/my", token),
        get<EligibleProduct[]>("/api/v1/sellers/me/eligible-products", token),
      ])
        .then(async ([myStores, eligibleProducts]) => {
          setEligible(eligibleProducts);
          if (myStores.length > 0) {
            const s = myStores[0];
            setStore(s);
            const inv = await get<StoreInventory[]>(
              `/api/v1/stores/${s.id}/inventory/all`,
              token,
            );
            const byProductId = new Map(
              eligibleProducts.map((p) => [p.id, p]),
            );
            setRows(
              inv
                .map((i) => {
                  const p = byProductId.get(i.product_id);
                  if (!p) return null;
                  const r: SheetRow = {
                    inventory_id: i.id,
                    product_id: p.id,
                    product_name: p.name,
                    service_name: p.service_name,
                    category_name: p.category_name,
                    subcategory_name: p.subcategory_name,
                    price: String(i.price),
                    stock: String(i.stock),
                    is_available: i.is_available,
                    dirty: false,
                    errors: {},
                  };
                  return r;
                })
                .filter((x): x is SheetRow => x !== null),
            );
          }
        })
        .catch(() => {})
        .finally(() => setFetching(false));
    }
  }, [authLoading, dbUser, token, router]);

  if (authLoading || fetching) {
    return (
      <div style={{ padding: "2rem", textAlign: "center" }}>Loading…</div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.toolbar}>
        <Link href="/seller/inventory" className="btn btn-outline">
          ← Single edit
        </Link>
        <button
          className="btn btn-primary"
          onClick={() => setPickerOpen(true)}
          disabled={!store}
        >
          + Add products
        </button>
        <button className="btn btn-primary" disabled={true}>
          Save
        </button>
      </div>

      <div className={styles.statusBar}>
        {rows.length} row(s)
      </div>

      <div className={styles.placeholder}>
        Sheet renders here (next task).
      </div>
    </div>
  );
}
```

Create `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css`:

```css
.page {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
}

.toolbar {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.statusBar {
  font-size: 0.875rem;
  color: var(--color-neutral-600);
}

.placeholder {
  border: 1px dashed var(--color-neutral-300);
  border-radius: var(--radius-md);
  padding: var(--space-6);
  text-align: center;
  color: var(--color-neutral-500);
}

.mobileBanner {
  display: none;
  padding: var(--space-3);
  background: var(--color-warning-50);
  border-radius: var(--radius-md);
  color: var(--color-warning-900);
  font-size: 0.875rem;
}

@media (max-width: 768px) {
  .mobileBanner {
    display: block;
  }
}
```

- [ ] **Step 2: Verify the page renders**

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000/seller/inventory/bulk` while logged in as an approved seller. Expected: toolbar + "X row(s)" + placeholder. No console errors.

Stop the dev server.

- [ ] **Step 3: Lint**

```bash
npm run lint
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/bulk/page.tsx frontend/src/app/\(operator\)/seller/inventory/bulk/bulk.module.css
git commit -m "feat(seller): add bulk inventory page shell"
```

---

## Task 11: `BulkInventorySheet` component

**Files:**
- Create: `frontend/src/app/(operator)/seller/inventory/bulk/BulkInventorySheet.tsx`
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css`

- [ ] **Step 1: Implement the sheet**

Create `frontend/src/app/(operator)/seller/inventory/bulk/BulkInventorySheet.tsx`:

```tsx
"use client";

import type { SheetRow } from "./page";
import styles from "./bulk.module.css";

interface Props {
  rows: SheetRow[];
  selectedIndices: Set<number>;
  onToggleSelect: (idx: number) => void;
  onPatchRow: (idx: number, patch: Partial<SheetRow>) => void;
  onRemoveRow: (idx: number) => void;
}

export function BulkInventorySheet({
  rows,
  selectedIndices,
  onToggleSelect,
  onPatchRow,
  onRemoveRow,
}: Props) {
  return (
    <div className={styles.sheetWrap}>
      <table className={styles.sheet}>
        <thead>
          <tr>
            <th></th>
            <th>Product</th>
            <th>Service</th>
            <th>Category</th>
            <th>Price (₹)</th>
            <th>Stock</th>
            <th>Available</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => {
            const isNew = row.inventory_id === null;
            const dirty = row.dirty;
            return (
              <tr
                key={`${row.product_id}-${idx}`}
                className={
                  dirty
                    ? isNew
                      ? styles.rowNew
                      : styles.rowDirty
                    : ""
                }
              >
                <td>
                  <input
                    type="checkbox"
                    checked={selectedIndices.has(idx)}
                    onChange={() => onToggleSelect(idx)}
                  />
                </td>
                <td>{row.product_name}</td>
                <td>{row.service_name}</td>
                <td>
                  {row.category_name} → {row.subcategory_name}
                </td>
                <td>
                  <input
                    type="number"
                    className={
                      row.errors.price ? styles.cellErr : styles.cell
                    }
                    value={row.price}
                    min="0.01"
                    step="0.01"
                    onChange={(e) =>
                      onPatchRow(idx, {
                        price: e.target.value,
                        dirty: true,
                        errors: validateCell(e.target.value, row.stock),
                      })
                    }
                  />
                  {row.errors.price && (
                    <div className={styles.cellErrMsg}>
                      {row.errors.price}
                    </div>
                  )}
                </td>
                <td>
                  <input
                    type="number"
                    className={
                      row.errors.stock ? styles.cellErr : styles.cell
                    }
                    value={row.stock}
                    min="0"
                    onChange={(e) =>
                      onPatchRow(idx, {
                        stock: e.target.value,
                        dirty: true,
                        errors: validateCell(row.price, e.target.value),
                      })
                    }
                  />
                  {row.errors.stock && (
                    <div className={styles.cellErrMsg}>
                      {row.errors.stock}
                    </div>
                  )}
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={row.is_available}
                    onChange={(e) =>
                      onPatchRow(idx, {
                        is_available: e.target.checked,
                        dirty: true,
                      })
                    }
                  />
                </td>
                <td>
                  {isNew && (
                    <button
                      className="btn btn-outline"
                      onClick={() => onRemoveRow(idx)}
                    >
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {rows.length === 0 && (
        <div className={styles.empty}>No rows. Click "Add products" to start.</div>
      )}
    </div>
  );
}

function validateCell(price: string, stock: string): SheetRow["errors"] {
  const errors: SheetRow["errors"] = {};
  const p = parseFloat(price);
  if (isNaN(p) || p <= 0 || p > 999999) {
    errors.price = "Price must be > 0 and ≤ 999999";
  }
  const s = parseInt(stock, 10);
  if (isNaN(s) || s < 0) {
    errors.stock = "Stock must be ≥ 0";
  }
  return errors;
}
```

- [ ] **Step 2: Append CSS for the sheet**

Append to `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css`:

```css
.sheetWrap {
  overflow-x: auto;
}

.sheet {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.sheet th,
.sheet td {
  padding: var(--space-2);
  border-bottom: 1px solid var(--color-neutral-200);
  text-align: left;
}

.cell {
  width: 100px;
  padding: 4px;
  border: 1px solid var(--color-neutral-300);
  border-radius: 4px;
}

.cellErr {
  width: 100px;
  padding: 4px;
  border: 1px solid var(--color-danger-500);
  border-radius: 4px;
}

.cellErrMsg {
  color: var(--color-danger-600);
  font-size: 0.75rem;
  margin-top: 2px;
}

.rowNew {
  background: var(--color-success-50);
}

.rowDirty {
  background: var(--color-warning-50);
}

.empty {
  padding: var(--space-6);
  text-align: center;
  color: var(--color-neutral-500);
}
```

- [ ] **Step 3: Wire the sheet into the page**

In `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`:

1. Add at the top with the other imports:

```tsx
import { BulkInventorySheet } from "./BulkInventorySheet";
```

2. Add this state alongside the existing `useState` calls:

```tsx
const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
```

3. Replace the `<div className={styles.placeholder}>Sheet renders here (next task).</div>` block with:

```tsx
<BulkInventorySheet
  rows={rows}
  selectedIndices={selectedIndices}
  onToggleSelect={(idx) => {
    setSelectedIndices((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }}
  onPatchRow={(idx, patch) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }}
  onRemoveRow={(idx) => {
    setRows((prev) => prev.filter((_, i) => i !== idx));
    setSelectedIndices((prev) => {
      const next = new Set<number>();
      prev.forEach((i) => { if (i !== idx) next.add(i < idx ? i : i - 1); });
      return next;
    });
  }}
/>
```

- [ ] **Step 4: Run lint**

```bash
npm run lint
```

Expected: clean.

- [ ] **Step 5: Smoke test in browser**

```bash
npm run dev
```

Visit `http://localhost:3000/seller/inventory/bulk`. Confirm: existing inventory rows render in the sheet. Edit a price — row turns yellow, errors show on invalid input. Stop the dev server.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/bulk/BulkInventorySheet.tsx frontend/src/app/\(operator\)/seller/inventory/bulk/page.tsx frontend/src/app/\(operator\)/seller/inventory/bulk/bulk.module.css
git commit -m "feat(seller): add editable BulkInventorySheet with per-cell validation"
```

---

## Task 12: `EligibleProductPicker` (drill-down side panel)

**Files:**
- Create: `frontend/src/app/(operator)/seller/inventory/bulk/EligibleProductPicker.tsx`
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css`

- [ ] **Step 1: Implement the picker**

Create `frontend/src/app/(operator)/seller/inventory/bulk/EligibleProductPicker.tsx`:

```tsx
"use client";

import { useMemo, useState } from "react";
import type { EligibleProduct } from "@/types";
import styles from "./bulk.module.css";

interface Props {
  open: boolean;
  products: EligibleProduct[];
  alreadyInSheet: Set<number>;
  onClose: () => void;
  onAdd: (selected: EligibleProduct[]) => void;
}

export function EligibleProductPicker({
  open,
  products,
  alreadyInSheet,
  onClose,
  onAdd,
}: Props) {
  const [search, setSearch] = useState("");
  const [serviceId, setServiceId] = useState<number | null>(null);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const services = useMemo(() => {
    const map = new Map<number, string>();
    products.forEach((p) => map.set(p.service_id, p.service_name));
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [products]);

  const categories = useMemo(() => {
    const map = new Map<number, { name: string; service_id: number }>();
    products.forEach((p) =>
      map.set(p.category_id, {
        name: p.category_name,
        service_id: p.service_id,
      }),
    );
    return Array.from(map.entries()).map(([id, v]) => ({ id, ...v }));
  }, [products]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return products.filter((p) => {
      if (alreadyInSheet.has(p.id) || p.in_inventory) return false;
      if (serviceId !== null && p.service_id !== serviceId) return false;
      if (categoryId !== null && p.category_id !== categoryId) return false;
      if (q && !p.name.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [products, alreadyInSheet, search, serviceId, categoryId]);

  if (!open) return null;

  return (
    <div className={styles.pickerBackdrop} onClick={onClose}>
      <div
        className={styles.pickerPanel}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.pickerHeader}>
          <strong>Add products to sheet</strong>
          <button className="btn btn-outline" onClick={onClose}>×</button>
        </div>
        <div className={styles.pickerFilters}>
          <input
            className={styles.cell}
            type="search"
            placeholder="Search products…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            value={serviceId ?? ""}
            onChange={(e) => {
              const v = e.target.value === "" ? null : Number(e.target.value);
              setServiceId(v);
              setCategoryId(null);
            }}
          >
            <option value="">All services</option>
            {services.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <select
            value={categoryId ?? ""}
            onChange={(e) =>
              setCategoryId(e.target.value === "" ? null : Number(e.target.value))
            }
            disabled={serviceId === null}
          >
            <option value="">All categories</option>
            {categories
              .filter((c) => serviceId === null || c.service_id === serviceId)
              .map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
          </select>
        </div>

        <div className={styles.pickerList}>
          {services.length === 0 && (
            <div className={styles.empty}>
              You haven't been approved for any services yet. Contact admin.
            </div>
          )}
          {filtered.map((p) => (
            <label key={p.id} className={styles.pickerRow}>
              <input
                type="checkbox"
                checked={selected.has(p.id)}
                onChange={() => {
                  setSelected((prev) => {
                    const next = new Set(prev);
                    if (next.has(p.id)) next.delete(p.id);
                    else next.add(p.id);
                    return next;
                  });
                }}
              />
              <span className={styles.pickerName}>{p.name}</span>
              <span className={styles.pickerMeta}>
                {p.service_name} · {p.category_name} · ₹{p.base_price}
              </span>
            </label>
          ))}
        </div>

        <div className={styles.pickerFooter}>
          <button className="btn btn-outline" onClick={onClose}>Cancel</button>
          <button
            className="btn btn-primary"
            disabled={selected.size === 0}
            onClick={() => {
              const chosen = products.filter((p) => selected.has(p.id));
              onAdd(chosen);
              setSelected(new Set());
            }}
          >
            Add {selected.size} to sheet
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Append picker CSS**

Append to `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css`:

```css
.pickerBackdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  justify-content: flex-end;
  z-index: 100;
}

.pickerPanel {
  width: min(480px, 90vw);
  background: var(--color-surface, #fff);
  display: flex;
  flex-direction: column;
  height: 100%;
}

.pickerHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-neutral-200);
}

.pickerFilters {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-neutral-200);
}

.pickerList {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2);
}

.pickerRow {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-2);
  border-bottom: 1px solid var(--color-neutral-100);
  cursor: pointer;
}

.pickerName {
  font-weight: 500;
}

.pickerMeta {
  color: var(--color-neutral-600);
  font-size: 0.75rem;
}

.pickerFooter {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  padding: var(--space-3);
  border-top: 1px solid var(--color-neutral-200);
}
```

- [ ] **Step 3: Wire picker into page**

In `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`:

1. Add to imports:

```tsx
import { EligibleProductPicker } from "./EligibleProductPicker";
```

2. Add this `useMemo` near the top of the component:

```tsx
const alreadyInSheet = useMemo(
  () => new Set(rows.map((r) => r.product_id)),
  [rows],
);
```

3. Add the picker at the bottom of the JSX, just before the final `</div>`:

```tsx
<EligibleProductPicker
  open={pickerOpen}
  products={eligible}
  alreadyInSheet={alreadyInSheet}
  onClose={() => setPickerOpen(false)}
  onAdd={(chosen) => {
    setRows((prev) => [
      ...prev,
      ...chosen.map<SheetRow>((p) => ({
        inventory_id: null,
        product_id: p.id,
        product_name: p.name,
        service_name: p.service_name,
        category_name: p.category_name,
        subcategory_name: p.subcategory_name,
        price: String(p.base_price),
        stock: "0",
        is_available: true,
        dirty: true,
        errors: {},
      })),
    ]);
    setPickerOpen(false);
  }}
/>
```

4. Add `useMemo` to the React imports if not already there.

- [ ] **Step 4: Lint + smoke test**

```bash
npm run lint
npm run dev
```

Open `/seller/inventory/bulk`, click "Add products", filter, check 2-3 rows, click "Add N to sheet". Confirm rows append as new (green). Stop dev server.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/bulk/EligibleProductPicker.tsx frontend/src/app/\(operator\)/seller/inventory/bulk/page.tsx frontend/src/app/\(operator\)/seller/inventory/bulk/bulk.module.css
git commit -m "feat(seller): add eligible product picker with service/category filters"
```

---

## Task 13: `BulkFillToolbar`

**Files:**
- Create: `frontend/src/app/(operator)/seller/inventory/bulk/BulkFillToolbar.tsx`
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css`

- [ ] **Step 1: Implement the toolbar**

Create `frontend/src/app/(operator)/seller/inventory/bulk/BulkFillToolbar.tsx`:

```tsx
"use client";

import { useState } from "react";
import styles from "./bulk.module.css";

export type BulkFillAction =
  | { kind: "set_price"; value: number }
  | { kind: "set_stock"; value: number }
  | { kind: "adjust_price_pct"; pct: number };

interface Props {
  selectedCount: number;
  onApply: (action: BulkFillAction) => void;
}

export function BulkFillToolbar({ selectedCount, onApply }: Props) {
  const [open, setOpen] = useState<null | "price" | "stock" | "pct">(null);
  const [value, setValue] = useState("");

  function submit(kind: "price" | "stock" | "pct") {
    const n = parseFloat(value);
    if (isNaN(n)) return;
    if (kind === "price") onApply({ kind: "set_price", value: n });
    else if (kind === "stock") onApply({ kind: "set_stock", value: Math.floor(n) });
    else onApply({ kind: "adjust_price_pct", pct: n });
    setValue("");
    setOpen(null);
  }

  return (
    <div className={styles.bulkFillWrap}>
      <span className={styles.bulkFillCount}>{selectedCount} selected</span>
      <button
        className="btn btn-outline"
        disabled={selectedCount === 0}
        onClick={() => setOpen(open === "price" ? null : "price")}
      >
        Set price…
      </button>
      <button
        className="btn btn-outline"
        disabled={selectedCount === 0}
        onClick={() => setOpen(open === "stock" ? null : "stock")}
      >
        Set stock…
      </button>
      <button
        className="btn btn-outline"
        disabled={selectedCount === 0}
        onClick={() => setOpen(open === "pct" ? null : "pct")}
      >
        Adjust price ±%…
      </button>

      {open !== null && (
        <div className={styles.bulkFillInline}>
          <input
            type="number"
            className={styles.cell}
            value={value}
            placeholder={
              open === "pct" ? "e.g. -10 for −10%" : open === "price" ? "Price" : "Stock"
            }
            onChange={(e) => setValue(e.target.value)}
          />
          <button className="btn btn-primary" onClick={() => submit(open)}>
            Apply
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Append CSS**

Append to `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css`:

```css
.bulkFillWrap {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-2) 0;
}

.bulkFillCount {
  font-size: 0.875rem;
  color: var(--color-neutral-600);
}

.bulkFillInline {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
```

- [ ] **Step 3: Wire into page**

In `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`:

1. Import:

```tsx
import { BulkFillToolbar, type BulkFillAction } from "./BulkFillToolbar";
```

2. Add `applyBulkFill` handler before the `return`:

```tsx
function applyBulkFill(action: BulkFillAction) {
  setRows((prev) =>
    prev.map((row, idx) => {
      if (!selectedIndices.has(idx)) return row;
      let next = { ...row, dirty: true };
      if (action.kind === "set_price") {
        next.price = String(action.value);
      } else if (action.kind === "set_stock") {
        next.stock = String(action.value);
      } else {
        const current = parseFloat(row.price);
        if (!isNaN(current)) {
          const updated = current * (1 + action.pct / 100);
          next.price = updated.toFixed(2);
        }
      }
      next.errors = {};
      const p = parseFloat(next.price);
      if (isNaN(p) || p <= 0 || p > 999999) next.errors.price = "Price must be > 0 and ≤ 999999";
      const s = parseInt(next.stock, 10);
      if (isNaN(s) || s < 0) next.errors.stock = "Stock must be ≥ 0";
      return next;
    }),
  );
}
```

3. Render the toolbar between the `statusBar` div and the sheet:

```tsx
<BulkFillToolbar
  selectedCount={selectedIndices.size}
  onApply={applyBulkFill}
/>
```

- [ ] **Step 4: Smoke test**

```bash
npm run lint
npm run dev
```

Visit page → check 2 rows → "Set price…" → enter 50 → Apply. Both rows show 50 and turn yellow. Stop dev server.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/bulk/BulkFillToolbar.tsx frontend/src/app/\(operator\)/seller/inventory/bulk/page.tsx frontend/src/app/\(operator\)/seller/inventory/bulk/bulk.module.css
git commit -m "feat(seller): add bulk-fill toolbar for set-price/stock/percent"
```

---

## Task 14: Wire Save (submit) + dirty-state guard + status counts

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`

- [ ] **Step 1: Add save logic, status counters, and unload guard**

In `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`:

1. Import `put` alongside the existing `get` import:

```tsx
import { get, put } from "@/lib/api";
```

(`@/lib/api` already exports `ApiError`; we don't need it here — the catch block uses a generic alert. Future tasks can refine error display.)

2. Add status counts via `useMemo`:

```tsx
const counts = useMemo(() => {
  let added = 0, edited = 0, invalid = 0;
  for (const r of rows) {
    const hasErr = Object.keys(r.errors).length > 0;
    if (hasErr) invalid++;
    if (r.dirty && !hasErr) {
      if (r.inventory_id === null) added++;
      else edited++;
    }
  }
  return { added, edited, invalid, total: rows.length };
}, [rows]);

const canSave = !saving && counts.invalid === 0 && (counts.added + counts.edited) > 0;
```

3. Replace the disabled "Save" button with a real handler:

```tsx
async function handleSave() {
  if (!store || !token) return;
  setSaving(true);
  try {
    const items: BulkInventoryItem[] = rows
      .filter((r) => r.dirty && Object.keys(r.errors).length === 0)
      .map((r) => ({
        product_id: r.product_id,
        price: parseFloat(r.price),
        stock: parseInt(r.stock, 10),
        is_available: r.is_available,
      }));
    if (items.length === 0) {
      setSaving(false);
      return;
    }
    const updated = await put<StoreInventory[]>(
      `/api/v1/stores/${store.id}/inventory/bulk`,
      { items },
      token,
    );
    const byProduct = new Map(updated.map((u) => [u.product_id, u]));
    setRows((prev) =>
      prev.map((r) => {
        const u = byProduct.get(r.product_id);
        if (!u) return r;
        return {
          ...r,
          inventory_id: u.id,
          price: String(u.price),
          stock: String(u.stock),
          is_available: u.is_available,
          dirty: false,
          errors: {},
        };
      }),
    );
  } catch (err) {
    // Server returned 4xx — show a banner. Detail format:
    //   {"detail": {"errors": [{index, product_id, code, message}]}}
    //   {"detail": {"code": "SERVICE_NOT_APPROVED", "product_ids": [...]}}
    console.error("bulk save failed", err);
    alert("Save failed. See errors flagged on rows.");
  } finally {
    setSaving(false);
  }
}
```

4. Replace the disabled save button:

```tsx
<button className="btn btn-primary" onClick={handleSave} disabled={!canSave}>
  {saving ? "Saving…" : `Save ${counts.added + counts.edited} change(s)`}
</button>
```

5. Update the status bar:

```tsx
<div className={styles.statusBar}>
  {counts.added} new · {counts.edited} edited · {counts.invalid} invalid · {counts.total} total
</div>
```

6. Add unload guard after the data fetch effect:

```tsx
useEffect(() => {
  const hasDirty = rows.some((r) => r.dirty);
  if (!hasDirty) return;
  const handler = (e: BeforeUnloadEvent) => {
    e.preventDefault();
    e.returnValue = "";
  };
  window.addEventListener("beforeunload", handler);
  return () => window.removeEventListener("beforeunload", handler);
}, [rows]);
```

- [ ] **Step 2: Lint + smoke**

```bash
npm run lint
npm run dev
```

End-to-end: open page → add 2 rows via picker → set prices → Save → confirm rows go from green/yellow to neutral and `inventory_id` populated (you can verify via the `/api/v1/stores/{id}/inventory/all` endpoint in another tab or by reloading the page). Stop dev server.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/bulk/page.tsx
git commit -m "feat(seller): wire bulk save, status counts, and unload guard"
```

---

## Task 15: Mobile banner

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`

- [ ] **Step 1: Add the banner above the toolbar**

In `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`, at the top of the returned JSX (just inside `<div className={styles.page}>`):

```tsx
<div className={styles.mobileBanner}>
  Bulk editor works best on a wider screen. Open from a desktop browser to use it comfortably.
</div>
```

The CSS class already exists in `bulk.module.css` from Task 10 and only displays under 768px.

- [ ] **Step 2: Resize browser → verify**

```bash
npm run dev
```

Visit page, narrow viewport below 768px — banner appears; widen — banner hides. Stop dev server.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/bulk/page.tsx
git commit -m "feat(seller): add mobile banner on bulk inventory editor"
```

---

## Task 16: Add "Bulk edit" link on the existing inventory page

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/page.tsx`

- [ ] **Step 1: Add the link**

In `frontend/src/app/(operator)/seller/inventory/page.tsx`, locate the toolbar block (around line 199-206 in the file as it currently exists):

```tsx
<div className={styles.toolbar}>
  <span className={styles.toolbarLeft}>
    {inventory.length} products in store
  </span>
  <button className={styles.addBtn} onClick={openAdd} disabled={availableProducts.length === 0}>
    + Add Product
  </button>
</div>
```

Replace it with:

```tsx
<div className={styles.toolbar}>
  <span className={styles.toolbarLeft}>
    {inventory.length} products in store
  </span>
  <Link href="/seller/inventory/bulk" className="btn btn-outline">
    Bulk edit →
  </Link>
  <button className={styles.addBtn} onClick={openAdd} disabled={availableProducts.length === 0}>
    + Add Product
  </button>
</div>
```

Add to imports at the top:

```tsx
import Link from "next/link";
```

- [ ] **Step 2: Lint + smoke**

```bash
npm run lint
npm run dev
```

Visit `/seller/inventory` → confirm "Bulk edit →" link sits beside "Add Product" → click → arrives at `/seller/inventory/bulk`. Stop dev server.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/page.tsx
git commit -m "feat(seller): link to bulk inventory editor from single-row page"
```

---

## Task 17: Update `docs/flows.md`

**Files:**
- Modify: `docs/flows.md`

- [ ] **Step 1: Append the new flow**

Append to `docs/flows.md`:

```markdown
## Seller bulk inventory edit

1. Seller opens `/seller/inventory/bulk` from the toolbar link on `/seller/inventory`.
2. Frontend loads:
   - `GET /api/v1/stores/my` → seller's store
   - `GET /api/v1/sellers/me/eligible-products` → products in seller's approved services (with `in_inventory` flag)
   - `GET /api/v1/stores/{id}/inventory/all` → existing rows
3. Existing rows render as editable sheet rows. Picker side panel offers add-from-eligible.
4. Seller edits prices/stocks (optionally using bulk-fill toolbar) and clicks Save.
5. Frontend pre-validates each row. Disabled-save until all rows valid AND ≥1 row dirty.
6. `PUT /api/v1/stores/{id}/inventory/bulk` body: `{ "items": [{ product_id, price, stock, is_available }] }`.
7. Server: authorize store ownership → enforce 200-row cap → field validation → service-membership check (`assert_products_in_seller_services`) → upsert in single transaction with row locks on existing rows (deterministic id order, same as checkout).
8. On any failure: HTTP 4xx with structured per-row errors; transaction rolled back; nothing persists.
9. On success: returns updated `StoreInventory` rows. Frontend clears dirty state and rebases sheet.

The single-row `POST /api/v1/stores/{id}/inventory` shares the same service-membership validator. Pre-existing rows that violate the new constraint are grandfathered (not deleted); operators can run `python -m app.db.scripts.audit_inventory_service_membership` to log them.
```

- [ ] **Step 2: Commit**

```bash
git add docs/flows.md
git commit -m "docs(flows): document seller bulk inventory edit flow"
```

---

## Task 18: Final integration check

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend/app
uv run pytest -v
```

Expected: all tests PASS (existing + new bulk + eligible-products tests).

- [ ] **Step 2: Backend lint + types**

```bash
uv run ruff check .
uv run mypy .
```

Expected: clean.

- [ ] **Step 3: Frontend lint + build**

```bash
cd ../../frontend
npm run lint
npm run build
```

Expected: build succeeds with no type errors.

- [ ] **Step 4: Manual end-to-end verification**

Start backend, celery, and frontend (`scripts/dev.sh` per `dev` skill). Log in as a seller approved for at least one service. Walk through:

1. Visit `/seller/inventory/bulk` — sheet shows existing rows.
2. Click "Add products" → drill-down picker scoped to approved services → check 5 products → "Add 5 to sheet" → 5 green rows appear.
3. Select 3 rows → "Set price…" → 99 → Apply → 3 rows turn yellow with price 99.
4. Click "Save 8 change(s)" → counts reset, rows go neutral, page refreshes show all 8 persisted.
5. Try to add a row by manually crafting a request to `PUT /inventory/bulk` for a product in a service the seller is NOT approved for (e.g., curl) → 403 SERVICE_NOT_APPROVED. (Optional sanity check; integration tests already cover this.)
6. Visit `/seller/inventory` (single page) → "Bulk edit →" link works in both directions.

- [ ] **Step 5: No-op commit if needed**

If any small fix-ups surfaced during integration, commit them now with descriptive messages (`fix:` or `chore:`). Otherwise nothing to commit.

---

## Spec Coverage Check

- Spec §2 Q1 (spreadsheet, no CSV) → Tasks 10-14
- Spec §2 Q2 (filter + drill-down picker) → Task 12
- Spec §2 Q3 (add + edit, no delete) → Tasks 11, 14
- Spec §2 Q4 (bulk-fill + default-to-base-price) → Tasks 12 (default = base_price), 13 (bulk-fill toolbar)
- Spec §2 Q5 (frontend pre-validate + server all-or-nothing) → Tasks 11, 14 (frontend); Task 6 (server txn)
- Spec §2 Q6 (single PUT bulk upsert) → Task 6
- Spec §2 Q7 (shared service-membership validator) → Tasks 2, 7
- Spec §2 Q8 (eligible-products endpoint) → Tasks 4, 5
- Spec §2 Q9 (200-row cap) → Task 6 (`_BULK_ROW_LIMIT`)
- Spec §2 Q10 (new sub-route) → Task 10; link from single-row in Task 16
- Spec §2 Q11 (mobile banner) → Task 15
- Spec §2 Q12 (lock_inventory_rows) → Task 3
- Spec §4.1 helpers → Tasks 2, 3
- Spec §4.2 endpoint → Tasks 4, 5
- Spec §4.3 endpoint + validation + 200-cap + structured errors → Task 6
- Spec §4.4 retrofit POST /inventory → Task 7
- Spec §4.5 schemas → Task 3 (Step 1)
- Spec §5 frontend → Tasks 9-15
- Spec §6 error handling → Tasks 6, 11, 14
- Spec §7 testing → Tasks 2, 3, 4, 5, 6, 7
- Spec §9 audit script → Task 8

All requirements mapped.
