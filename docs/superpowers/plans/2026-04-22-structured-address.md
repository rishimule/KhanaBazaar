<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Structured Address Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single free-text `address: str` column on `SellerProfile` and `Store` with a structured 9-field address (line1/line2/landmark/city/state/pincode/country/lat/lng), exposed as a nested `address` object in all API request/response bodies and rendered by a shared `<AddressFields>` React component on the frontend.

**Architecture:** Flat DB columns on each owner table via a shared `AddressBase` SQLModel mixin. A separate `AddressPayload` Pydantic schema (same 9 fields, same validators) is used as the nested API shape. Frontend mirrors the wire shape with an `Address` TypeScript interface and renders via one shared form component backed by a cached `/meta/indian-states` list. One Alembic migration truncates the `sellerprofile` and `store` tables (pre-production) and swaps the columns cleanly, with no placeholder defaults.

**Tech Stack:** FastAPI, SQLModel, Alembic, asyncpg, Pydantic v2, Pytest, Next.js 16 App Router, TypeScript, CSS Modules.

---

## File Structure

### Backend files to create

- `backend/app/src/app/core/indian_states.py` — module-level `INDIAN_STATES: list[str]` (28 states + 8 UTs, alphabetical).
- `backend/app/src/app/schemas/__init__.py` — (empty, marks package).
- `backend/app/src/app/schemas/address.py` — `AddressPayload` Pydantic model + `address_from_payload` / `address_to_payload` converters that map the nested payload to/from a dict of flat column names.
- `backend/app/src/app/schemas/stores.py` — `StoreCreate`, `StoreRead` Pydantic models with nested `address: AddressPayload` (Store API currently uses `Store` directly as the body type, which cannot remain once the DB shape is flat and the wire shape is nested).
- `backend/app/src/app/schemas/sellers.py` — `SellerRegisterBody`, `SellerProfileUpdateBody`, `SellerProfilePayload`, `SellerApplicationPayload` with nested `address: AddressPayload`.
- `backend/app/src/app/utils/__init__.py` — (empty).
- `backend/app/src/app/utils/address.py` — `format_address(addr) -> str`.
- `backend/app/src/app/api/meta.py` — `GET /meta/indian-states`.
- `backend/app/migrations/versions/abc123456789_split_address_fields.py` — Alembic revision.
- `backend/app/tests/test_address_validator.py` — Pydantic validator tests.
- `backend/app/tests/test_indian_states.py` — constant integrity test.
- `backend/app/tests/test_format_address.py` — formatter tests.
- `backend/app/tests/test_meta.py` — states endpoint test.
- `backend/app/tests/_helpers.py` — shared `make_address()` factory.

### Backend files to modify

- `backend/app/src/app/models/seller.py` — drop `address: str`, mix in `AddressBase`.
- `backend/app/src/app/models/store.py` — drop `address: str`, mix in `AddressBase`.
- `backend/app/src/app/api/auth.py` — `SellerRegisterBody` uses nested `address`; `seller_register` maps payload to flat columns.
- `backend/app/src/app/api/sellers.py` — profile GET/PATCH uses nested `address`; admin applications payload uses nested `address`.
- `backend/app/src/app/api/stores.py` — list/get/create use nested-address request/response models.
- `backend/app/src/app/api/__init__.py` — register `meta` router.
- `backend/app/tests/test_seller_register.py` — payload uses nested `address`.
- `backend/app/tests/test_seller_status.py` — update if it exercises address (verify after running).
- `backend/app/tests/test_stores.py` — create/get tests use nested `address`.

### Frontend files to create

- `frontend/src/lib/format-address.ts` — `formatAddress(addr) -> string` mirroring backend.
- `frontend/src/lib/indian-states.ts` — one-time cached fetch.
- `frontend/src/components/AddressFields.tsx` — shared form component.
- `frontend/src/components/AddressFields.module.css` — styles.

### Frontend files to modify

- `frontend/src/types/index.ts` — add `Address`; change `Store.address`, `SellerProfile.address`, `SellerApplication.address` from `string` to `Address`.
- `frontend/src/app/seller/signup/page.tsx` — replace flat `address: string` with `address: Address`; swap single input for `<AddressFields>` on step 4; render formatted string on step 6; update register/patch bodies.
- `frontend/src/app/admin/sellers/page.tsx` — render structured address block in the review modal details grid.
- `frontend/src/app/stores/page.tsx` — render via `formatAddress`.
- `frontend/src/app/stores/[id]/page.tsx` — render via `formatAddress`.
- `frontend/src/app/page.tsx` — render via `formatAddress` wherever a store address is shown.
- `frontend/src/app/sell/page.tsx` — render via `formatAddress` wherever a store address is shown.
- `frontend/src/lib/mock-data.ts` — mock stores updated to the structured shape.

---

## Task 1: Add `INDIAN_STATES` constants

**Files:**
- Create: `backend/app/src/app/core/indian_states.py`
- Test: `backend/app/tests/test_indian_states.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_indian_states.py
from app.core.indian_states import INDIAN_STATES


def test_indian_states_has_36_entries() -> None:
    assert len(INDIAN_STATES) == 36


def test_indian_states_contains_expected_names() -> None:
    assert "Maharashtra" in INDIAN_STATES
    assert "Delhi" in INDIAN_STATES
    assert "Tamil Nadu" in INDIAN_STATES
    assert "Jammu and Kashmir" in INDIAN_STATES


def test_indian_states_is_alphabetical() -> None:
    assert INDIAN_STATES == sorted(INDIAN_STATES)


def test_indian_states_are_unique() -> None:
    assert len(set(INDIAN_STATES)) == len(INDIAN_STATES)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_indian_states.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.indian_states'`.

- [ ] **Step 3: Create the constants module**

```python
# backend/app/src/app/core/indian_states.py
"""List of Indian states and Union Territories, alphabetical.

Source of truth for the `state` field on structured addresses. Keep
alphabetical so the frontend dropdown renders in predictable order.
"""

INDIAN_STATES: list[str] = [
    "Andaman and Nicobar Islands",
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chandigarh",
    "Chhattisgarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jammu and Kashmir",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Lakshadweep",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Puducherry",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend/app && uv run pytest tests/test_indian_states.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/core/indian_states.py backend/app/tests/test_indian_states.py
git commit -m "feat(address): add INDIAN_STATES constant"
```

---

## Task 2: Add `AddressPayload` Pydantic schema + validators

**Files:**
- Create: `backend/app/src/app/schemas/__init__.py`
- Create: `backend/app/src/app/schemas/address.py`
- Test: `backend/app/tests/test_address_validator.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_address_validator.py
import pytest
from pydantic import ValidationError

from app.schemas.address import AddressPayload


def _valid_dict(**overrides: object) -> dict:
    base = {
        "address_line1": "12 MG Road",
        "address_line2": "Sector 14",
        "landmark": "Near Cyber Hub",
        "city": "Gurugram",
        "state": "Haryana",
        "pincode": "122001",
        "country": "India",
        "latitude": 28.4595,
        "longitude": 77.0266,
    }
    base.update(overrides)
    return base


def test_valid_address_passes() -> None:
    addr = AddressPayload(**_valid_dict())
    assert addr.pincode == "122001"


def test_optional_fields_accept_none() -> None:
    addr = AddressPayload(**_valid_dict(address_line2=None, landmark=None, latitude=None, longitude=None))
    assert addr.address_line2 is None
    assert addr.landmark is None
    assert addr.latitude is None
    assert addr.longitude is None


def test_india_pincode_leading_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(pincode="023456"))


def test_india_pincode_five_digits_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(pincode="12345"))


def test_india_pincode_non_numeric_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(pincode="abcdef"))


def test_non_india_country_accepts_other_postal_format() -> None:
    addr = AddressPayload(**_valid_dict(country="Nepal", state="Bagmati", pincode="44600"))
    assert addr.country == "Nepal"


def test_india_state_not_in_list_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(state="Atlantis"))


def test_non_india_state_free_text_accepted() -> None:
    addr = AddressPayload(**_valid_dict(country="Nepal", state="Bagmati", pincode="44600"))
    assert addr.state == "Bagmati"


def test_latitude_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(latitude=91.0))


def test_longitude_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(longitude=-181.0))


def test_required_field_missing_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(address_line1=""))


def test_address_line1_max_length_enforced() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(address_line1="x" * 121))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_address_validator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas'`.

- [ ] **Step 3: Create the schemas package marker**

```python
# backend/app/src/app/schemas/__init__.py
```

(Empty file.)

- [ ] **Step 4: Implement `AddressPayload`**

```python
# backend/app/src/app/schemas/address.py
"""Pydantic schema for the structured address wire format.

Used as the nested `address` object on every API request/response body
that carries a seller or store address. The DB stores these fields as
flat columns (see `app.models.address.AddressBase`); the converters at
the bottom translate between the two shapes.
"""

import re
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.core.indian_states import INDIAN_STATES

_INDIA_PINCODE_RE = re.compile(r"^[1-9]\d{5}$")
_NON_INDIA_PINCODE_RE = re.compile(r"^[A-Za-z0-9\- ]{3,10}$")


class AddressPayload(BaseModel):
    address_line1: str = Field(min_length=1, max_length=120)
    address_line2: Optional[str] = Field(default=None, max_length=120)
    landmark: Optional[str] = Field(default=None, max_length=120)
    city: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=80)
    pincode: str = Field(min_length=3, max_length=10)
    country: str = Field(default="India", min_length=1, max_length=60)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)

    @model_validator(mode="after")
    def _check_country_specific_rules(self) -> "AddressPayload":
        if self.country == "India":
            if not _INDIA_PINCODE_RE.match(self.pincode):
                raise ValueError("pincode must be 6 digits with no leading zero for India")
            if self.state not in INDIAN_STATES:
                raise ValueError("state must be an Indian state or Union Territory")
        else:
            if not _NON_INDIA_PINCODE_RE.match(self.pincode):
                raise ValueError("pincode must be 3-10 alphanumeric characters")
        return self


_ADDRESS_FIELDS: tuple[str, ...] = (
    "address_line1",
    "address_line2",
    "landmark",
    "city",
    "state",
    "pincode",
    "country",
    "latitude",
    "longitude",
)


def address_from_payload(payload: AddressPayload) -> dict[str, object]:
    """Flatten the nested payload to the column names used on owner tables."""
    return {field: getattr(payload, field) for field in _ADDRESS_FIELDS}


def address_to_payload(owner: object) -> AddressPayload:
    """Build a nested payload from an owner object carrying the flat columns."""
    return AddressPayload(**{field: getattr(owner, field) for field in _ADDRESS_FIELDS})
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend/app && uv run pytest tests/test_address_validator.py -v`
Expected: 11 PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/schemas backend/app/tests/test_address_validator.py
git commit -m "feat(address): add AddressPayload schema and validators"
```

---

## Task 3: Add `format_address` utility

**Files:**
- Create: `backend/app/src/app/utils/__init__.py`
- Create: `backend/app/src/app/utils/address.py`
- Test: `backend/app/tests/test_format_address.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_format_address.py
from app.schemas.address import AddressPayload
from app.utils.address import format_address


def _payload(**overrides: object) -> AddressPayload:
    base = {
        "address_line1": "12 MG Road",
        "address_line2": "Sector 14",
        "landmark": "Near Cyber Hub",
        "city": "Gurugram",
        "state": "Haryana",
        "pincode": "122001",
        "country": "India",
        "latitude": None,
        "longitude": None,
    }
    base.update(overrides)
    return AddressPayload(**base)


def test_format_full_address() -> None:
    assert format_address(_payload()) == (
        "12 MG Road, Sector 14, Near Cyber Hub, Gurugram, Haryana 122001, India"
    )


def test_format_without_optional_parts() -> None:
    assert format_address(_payload(address_line2=None, landmark=None)) == (
        "12 MG Road, Gurugram, Haryana 122001, India"
    )


def test_format_strips_empty_optional_strings() -> None:
    assert format_address(_payload(address_line2="", landmark="   ")) == (
        "12 MG Road, Gurugram, Haryana 122001, India"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_format_address.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.utils'`.

- [ ] **Step 3: Create the utils package marker**

```python
# backend/app/src/app/utils/__init__.py
```

(Empty file.)

- [ ] **Step 4: Implement the formatter**

```python
# backend/app/src/app/utils/address.py
"""Pretty single-line formatter for structured addresses."""

from app.schemas.address import AddressPayload


def format_address(addr: AddressPayload) -> str:
    parts: list[str] = [addr.address_line1]
    for optional in (addr.address_line2, addr.landmark):
        if optional and optional.strip():
            parts.append(optional.strip())
    parts.append(addr.city)
    parts.append(f"{addr.state} {addr.pincode}")
    parts.append(addr.country)
    return ", ".join(parts)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend/app && uv run pytest tests/test_format_address.py -v`
Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/utils backend/app/tests/test_format_address.py
git commit -m "feat(address): add format_address utility"
```

---

## Task 4: Add `AddressBase` SQLModel mixin and apply to models

**Files:**
- Create: `backend/app/src/app/models/address.py`
- Modify: `backend/app/src/app/models/seller.py`
- Modify: `backend/app/src/app/models/store.py`
- Create: `backend/app/tests/_helpers.py`

- [ ] **Step 1: Create the `_helpers.py` test factory**

This helper is used by many downstream tests to produce a valid flat address dict (matching DB column names) or a nested payload dict.

```python
# backend/app/tests/_helpers.py
"""Shared test factories."""


def make_address(**overrides: object) -> dict:
    base = {
        "address_line1": "12 MG Road",
        "address_line2": "Sector 14",
        "landmark": "Near Cyber Hub",
        "city": "Gurugram",
        "state": "Haryana",
        "pincode": "122001",
        "country": "India",
        "latitude": 28.4595,
        "longitude": 77.0266,
    }
    base.update(overrides)
    return base
```

- [ ] **Step 2: Create the `AddressBase` mixin**

```python
# backend/app/src/app/models/address.py
"""Shared address columns applied as a mixin on owner tables.

The 9 columns mirror the `AddressPayload` Pydantic schema. Validation
for incoming wire-format data lives on the schema; this mixin only
defines DB column nullability. Owner tables inherit this mixin
alongside `BaseSchema`.
"""

from typing import Optional

from sqlmodel import Field, SQLModel


class AddressBase(SQLModel):
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

- [ ] **Step 3: Update `SellerProfile` to use the mixin**

Replace the current contents of `backend/app/src/app/models/seller.py` with:

```python
import enum
from typing import Optional

from sqlmodel import Field, Relationship

from app.models.address import AddressBase
from app.models.base import BaseSchema, User


class VerificationStatus(str, enum.Enum):
    Pending = "pending"
    Approved = "approved"
    Rejected = "rejected"


class SellerProfile(BaseSchema, AddressBase, table=True):
    user_id: int = Field(foreign_key="user.id", unique=True, nullable=False)
    business_name: str = Field(nullable=False)
    business_category: str = Field(nullable=False)
    phone: str = Field(nullable=False)
    gst_number: str = Field(nullable=False)
    fssai_license: str = Field(nullable=False)
    bank_account_number: str = Field(nullable=False)
    bank_ifsc: str = Field(nullable=False)
    verification_status: VerificationStatus = Field(default=VerificationStatus.Pending)
    rejection_reason: Optional[str] = Field(default=None)

    user: User = Relationship()
```

- [ ] **Step 4: Update `Store` to use the mixin**

Replace the current `Store` class in `backend/app/src/app/models/store.py` with:

```python
from typing import List

from sqlmodel import Field, Relationship, UniqueConstraint

from app.models.address import AddressBase
from app.models.base import BaseSchema, User
from app.models.catalog import MasterProduct


class Store(BaseSchema, AddressBase, table=True):
    name: str = Field(index=True, nullable=False)
    is_active: bool = Field(default=True)
    seller_id: int = Field(foreign_key="user.id", nullable=False)

    # Relationships
    seller: User = Relationship()
    inventories: List["StoreInventory"] = Relationship(back_populates="store")


class StoreInventory(BaseSchema, table=True):
    __table_args__ = (
        UniqueConstraint("store_id", "product_id", name="uq_store_product"),
    )
    store_id: int = Field(foreign_key="store.id", nullable=False)
    product_id: int = Field(foreign_key="masterproduct.id", nullable=False)
    price: float = Field(nullable=False)
    stock: int = Field(default=0, nullable=False)
    is_available: bool = Field(default=True)

    # Relationships
    store: Store = Relationship(back_populates="inventories")
    product: MasterProduct = Relationship(back_populates="inventories")
```

- [ ] **Step 5: Run type check to verify models compile**

Run: `cd backend/app && uv run mypy .`
Expected: pass (no type errors). Mypy may report errors elsewhere from the other API/test changes that come in later tasks — ignore those and only confirm no errors come from `models/seller.py`, `models/store.py`, or `models/address.py`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/models/address.py backend/app/src/app/models/seller.py backend/app/src/app/models/store.py backend/app/tests/_helpers.py
git commit -m "feat(address): add AddressBase mixin and apply to SellerProfile and Store"
```

---

## Task 5: Alembic migration — split address fields

**Files:**
- Create: `backend/app/migrations/versions/abc123456789_split_address_fields.py`

- [ ] **Step 1: Generate the revision skeleton**

Run: `cd backend/app && uv run alembic revision -m "split address fields" --rev-id abc123456789`
Expected: a new file created under `backend/app/migrations/versions/abc123456789_split_address_fields.py`. Confirm its `down_revision` is set to `d6342a56eaf6` (the current head). If not, edit it manually.

- [ ] **Step 2: Replace the generated body with the structured-split migration**

Open `backend/app/migrations/versions/abc123456789_split_address_fields.py` and replace everything below the identifier block with:

```python
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "abc123456789"
down_revision: Union[str, Sequence[str], None] = "d6342a56eaf6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADDRESS_COLUMNS_REQUIRED = (
    ("address_line1", sa.String(length=120)),
    ("city", sa.String(length=80)),
    ("state", sa.String(length=80)),
    ("pincode", sa.String(length=10)),
    ("country", sa.String(length=60)),
)

ADDRESS_COLUMNS_OPTIONAL = (
    ("address_line2", sa.String(length=120)),
    ("landmark", sa.String(length=120)),
    ("latitude", sa.Float()),
    ("longitude", sa.Float()),
)


def upgrade() -> None:
    """Replace the free-text `address` column with structured fields.

    Pre-production only: truncates `sellerprofile` and `store` so the
    new NOT NULL columns can be added cleanly without placeholder
    defaults that would violate app-level validators.
    """
    op.execute("TRUNCATE sellerprofile, store RESTART IDENTITY CASCADE")

    op.drop_column("sellerprofile", "address")
    op.drop_column("store", "address")

    for table in ("sellerprofile", "store"):
        for name, col_type in ADDRESS_COLUMNS_REQUIRED:
            op.add_column(table, sa.Column(name, col_type, nullable=False))
        for name, col_type in ADDRESS_COLUMNS_OPTIONAL:
            op.add_column(table, sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    """Reverse the split. Lossy: structured data cannot be recombined."""
    for table in ("sellerprofile", "store"):
        for name, _col_type in ADDRESS_COLUMNS_OPTIONAL:
            op.drop_column(table, name)
        for name, _col_type in ADDRESS_COLUMNS_REQUIRED:
            op.drop_column(table, name)
        op.add_column(
            table,
            sa.Column("address", sa.String(), nullable=False, server_default=""),
        )
        op.alter_column(table, "address", server_default=None)
```

- [ ] **Step 3: Apply the migration locally**

Run: `cd backend/app && uv run alembic upgrade head`
Expected: migration runs without error; `psql` shows the 9 new columns on both tables and no `address` column.

Verify: `PGPASSWORD=password psql -h localhost -U postgres -d khanabazaar -c "\d sellerprofile" | grep -E 'address_line1|pincode'`
Expected: both column names appear.

- [ ] **Step 4: Commit**

```bash
git add backend/app/migrations/versions/abc123456789_split_address_fields.py
git commit -m "feat(address): alembic migration to split address into structured fields"
```

---

## Task 6: Meta API — `GET /meta/indian-states`

**Files:**
- Create: `backend/app/src/app/api/meta.py`
- Modify: `backend/app/src/app/api/__init__.py`
- Test: `backend/app/tests/test_meta.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_meta.py
import pytest
from httpx import ASGITransport, AsyncClient

from app import app


@pytest.mark.asyncio
async def test_indian_states_endpoint_returns_36_entries() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/meta/indian-states")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["states"]) == 36
    assert "Maharashtra" in data["states"]
    assert "Delhi" in data["states"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_meta.py -v`
Expected: FAIL with 404 (route not registered).

- [ ] **Step 3: Implement the router**

```python
# backend/app/src/app/api/meta.py
from fastapi import APIRouter

from app.core.indian_states import INDIAN_STATES

router = APIRouter()


@router.get("/indian-states")
async def get_indian_states() -> dict[str, list[str]]:
    return {"states": INDIAN_STATES}
```

- [ ] **Step 4: Register the router**

Replace the contents of `backend/app/src/app/api/__init__.py` with:

```python
from fastapi import APIRouter

from app.api import auth, catalog, meta, sellers, stores, tasks

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
api_router.include_router(stores.router, prefix="/stores", tags=["stores"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(sellers.router, prefix="/sellers", tags=["sellers"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend/app && uv run pytest tests/test_meta.py -v`
Expected: PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/api/meta.py backend/app/src/app/api/__init__.py backend/app/tests/test_meta.py
git commit -m "feat(address): add GET /meta/indian-states"
```

---

## Task 7: Sellers & Auth schemas with nested address

**Files:**
- Create: `backend/app/src/app/schemas/sellers.py`
- Modify: `backend/app/src/app/api/auth.py`
- Modify: `backend/app/src/app/api/sellers.py`
- Modify: `backend/app/tests/test_seller_register.py`

This task switches the seller endpoints to nested-address wire format. Multiple sites change together because any partial state (some endpoints nested, others flat) would leave the app incoherent.

- [ ] **Step 1: Write the failing test (register + profile GET)**

Replace the contents of `backend/app/tests/test_seller_register.py` with:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from app.core.security import create_access_token, create_email_verification_token
from app.models.base import User, UserRole
from tests._helpers import make_address

REGISTER_PAYLOAD = {
    "full_name": "Priya Verma",
    "phone": "9876543210",
    "business_name": "Priya's Grocery",
    "business_category": "grocery",
    "address": make_address(),
    "gst_number": "29ABCDE1234F1Z5",
    "fssai_license": "10020042000015",
    "bank_account_number": "123456789012",
    "bank_ifsc": "SBIN0001234",
}


@pytest.mark.asyncio
async def test_seller_register_happy_path_returns_nested_address_on_profile() -> None:
    email_token = create_email_verification_token("seller@test.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": email_token, **REGISTER_PAYLOAD},
        )
        assert resp.status_code == 200
        token = resp.json()["access_token"]

        profile_resp = await ac.get(
            "/api/v1/sellers/me/profile",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["address"] == REGISTER_PAYLOAD["address"]


@pytest.mark.asyncio
async def test_seller_register_rejects_missing_address_line1() -> None:
    email_token = create_email_verification_token("bad@test.com")
    bad_address = make_address(address_line1="")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": email_token, **{**REGISTER_PAYLOAD, "address": bad_address}},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_seller_register_rejects_invalid_pincode() -> None:
    email_token = create_email_verification_token("pin@test.com")
    bad_address = make_address(pincode="12345")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": email_token, **{**REGISTER_PAYLOAD, "address": bad_address}},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_seller_register_duplicate_email() -> None:
    payload = {"email_token": create_email_verification_token("dup@test.com"), **REGISTER_PAYLOAD}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/auth/seller/register", json=payload)
        payload["email_token"] = create_email_verification_token("dup@test.com")
        resp = await ac.post("/api/v1/auth/seller/register", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_seller_register_invalid_token() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": "not.a.real.token", **REGISTER_PAYLOAD},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_seller_register_wrong_token_type() -> None:
    from datetime import datetime, timedelta, timezone

    import jwt as pyjwt

    from app.core.config import settings

    bad_token = pyjwt.encode(
        {"sub": "x@test.com", "type": "access", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": bad_token, **REGISTER_PAYLOAD},
        )
    assert resp.status_code == 400


# Needed so the profile fetch can hit the seller-only endpoint.
_ = (User, UserRole, create_access_token)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_seller_register.py -v`
Expected: multiple failures (tests send `address` as a dict but `SellerRegisterBody` still types it as `str`, producing 422 mismatches, and profile response still returns flat columns).

- [ ] **Step 3: Create the seller schemas**

```python
# backend/app/src/app/schemas/sellers.py
"""Wire-format models for seller endpoints.

These sit on the boundary between the API and the DB; the DB stores
address columns flat and these models expose them as a nested
`address` object.
"""

from typing import Optional

from pydantic import BaseModel, EmailStr

from app.schemas.address import AddressPayload


class SellerRegisterBody(BaseModel):
    email_token: str
    full_name: str
    phone: str
    business_name: str
    business_category: str
    address: AddressPayload
    gst_number: str
    fssai_license: str
    bank_account_number: str
    bank_ifsc: str


class SellerProfileUpdateBody(BaseModel):
    business_name: str
    business_category: str
    address: AddressPayload
    phone: str
    gst_number: str
    fssai_license: str
    bank_account_number: str
    bank_ifsc: str


class SellerProfilePayload(BaseModel):
    id: int
    user_id: int
    business_name: str
    business_category: str
    address: AddressPayload
    phone: str
    gst_number: str
    fssai_license: str
    bank_account_number: str
    bank_ifsc: str
    verification_status: str
    rejection_reason: Optional[str] = None


class SellerApplicationPayload(BaseModel):
    seller_id: int
    email: EmailStr
    full_name: Optional[str] = None
    business_name: str
    business_category: str
    address: AddressPayload
    phone: str
    gst_number: str
    fssai_license: str
    bank_account_number: str
    bank_ifsc: str
    verification_status: str
    rejection_reason: Optional[str] = None
    submitted_at: Optional[str] = None
    updated_at: Optional[str] = None
```

- [ ] **Step 4: Update `auth.py` seller register to use the nested schema**

In `backend/app/src/app/api/auth.py`, replace the `SellerRegisterBody` class and the `seller_register` function body with:

```python
# --- top of file: add these imports alongside existing ones ---
from app.schemas.address import address_from_payload
from app.schemas.sellers import SellerRegisterBody as _SellerRegisterBody


# --- replace the old SellerRegisterBody class with: ---
SellerRegisterBody = _SellerRegisterBody  # re-exported for tests that imported the old symbol


# --- replace the seller_register function body with: ---
@router.post("/seller/register")
async def seller_register(
    body: SellerRegisterBody,
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    email = decode_email_verification_token(body.email_token)

    result = await session.exec(select(User).where(User.email == email))
    if result.first():
        raise HTTPException(status_code=409, detail={"error": "email_already_registered"})

    user = User(email=email, full_name=body.full_name.strip(), role=UserRole.Seller)
    session.add(user)
    await session.flush()

    profile = SellerProfile(
        user_id=user.id,
        business_name=body.business_name,
        business_category=body.business_category,
        phone=body.phone,
        gst_number=body.gst_number,
        fssai_license=body.fssai_license,
        bank_account_number=body.bank_account_number,
        bank_ifsc=body.bank_ifsc,
        **address_from_payload(body.address),
    )
    session.add(profile)
    await session.commit()
    await session.refresh(user)

    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user.model_dump(),
    }
```

Concretely: the imports at the top of `auth.py` gain two lines, the old `SellerRegisterBody` class (lines 48-58 of the original file) is removed, and the `seller_register` handler (lines 145-180) is replaced with the version above. Leave the rest of `auth.py` untouched.

- [ ] **Step 5: Update `sellers.py` profile endpoints to nested shape**

In `backend/app/src/app/api/sellers.py`, make these changes:

1. Add imports near the top:

```python
from app.schemas.address import address_from_payload, address_to_payload
from app.schemas.sellers import (
    SellerApplicationPayload,
    SellerProfilePayload,
    SellerProfileUpdateBody as _SellerProfileUpdateBody,
)
```

2. Remove the existing `SellerProfileUpdateBody` class (lines 48-56 of the current file) and add:

```python
SellerProfileUpdateBody = _SellerProfileUpdateBody
```

3. Replace `get_seller_profile` with:

```python
@router.get("/me/profile", response_model=SellerProfilePayload)
async def get_seller_profile(
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> SellerProfilePayload:
    result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == current_user.id)
    )
    profile = result.first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    return SellerProfilePayload(
        id=profile.id,
        user_id=profile.user_id,
        business_name=profile.business_name,
        business_category=profile.business_category,
        address=address_to_payload(profile),
        phone=profile.phone,
        gst_number=profile.gst_number,
        fssai_license=profile.fssai_license,
        bank_account_number=profile.bank_account_number,
        bank_ifsc=profile.bank_ifsc,
        verification_status=profile.verification_status.value,
        rejection_reason=profile.rejection_reason,
    )
```

4. Replace `update_seller_profile` with:

```python
@router.patch("/me/profile")
async def update_seller_profile(
    body: SellerProfileUpdateBody,
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == current_user.id)
    )
    profile = result.first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    profile.business_name = body.business_name
    profile.business_category = body.business_category
    profile.phone = body.phone
    profile.gst_number = body.gst_number
    profile.fssai_license = body.fssai_license
    profile.bank_account_number = body.bank_account_number
    profile.bank_ifsc = body.bank_ifsc
    for key, value in address_from_payload(body.address).items():
        setattr(profile, key, value)
    profile.verification_status = VerificationStatus.Pending
    profile.rejection_reason = None

    await session.commit()
    await session.refresh(profile)
    return {
        "verification_status": profile.verification_status,
        "rejection_reason": profile.rejection_reason,
    }
```

5. Replace `_application_payload` with:

```python
def _application_payload(profile: SellerProfile, user: User) -> dict:  # type: ignore[type-arg]
    return SellerApplicationPayload(
        seller_id=user.id,
        email=user.email,
        full_name=user.full_name,
        business_name=profile.business_name,
        business_category=profile.business_category,
        address=address_to_payload(profile),
        phone=profile.phone,
        gst_number=profile.gst_number,
        fssai_license=profile.fssai_license,
        bank_account_number=profile.bank_account_number,
        bank_ifsc=profile.bank_ifsc,
        verification_status=profile.verification_status.value,
        rejection_reason=profile.rejection_reason,
        submitted_at=profile.created_at.isoformat() if profile.created_at else None,
        updated_at=profile.updated_at.isoformat() if profile.updated_at else None,
    ).model_dump()
```

- [ ] **Step 6: Run the register tests to verify they pass**

Run: `cd backend/app && uv run pytest tests/test_seller_register.py -v`
Expected: 6 PASSED.

- [ ] **Step 7: Run the full seller test suite to catch regressions**

Run: `cd backend/app && uv run pytest tests/test_seller_status.py tests/test_admin_applications.py tests/test_admin_verify.py -v`
Expected: PASSED. If any test fails because it sends a flat `address: str` or reads a flat field, fix the test to use `make_address()` from `tests/_helpers.py` and nested `address` in the response.

- [ ] **Step 8: Commit**

```bash
git add backend/app/src/app/schemas/sellers.py backend/app/src/app/api/auth.py backend/app/src/app/api/sellers.py backend/app/tests/test_seller_register.py backend/app/tests/test_seller_status.py backend/app/tests/test_admin_applications.py backend/app/tests/test_admin_verify.py
git commit -m "feat(address): nest address payload on seller register, profile, and admin endpoints"
```

(Omit any path from the `git add` line that did not actually change.)

---

## Task 8: Stores API with nested address

**Files:**
- Create: `backend/app/src/app/schemas/stores.py`
- Modify: `backend/app/src/app/api/stores.py`
- Modify: `backend/app/tests/test_stores.py`

- [ ] **Step 1: Inspect the existing test file to understand the test fixtures**

Run: `grep -n "address" backend/app/tests/test_stores.py`
Expected: one or more occurrences of the flat `"address": "..."` string in request payloads; note every line number.

- [ ] **Step 2: Write the failing tests**

Replace every flat `"address": "some string"` entry inside `backend/app/tests/test_stores.py` with:

```python
"address": make_address(),
```

Add this import at the top of the file (if not already present):

```python
from tests._helpers import make_address
```

Also add three new tests (append to the end of the file, using the existing fixture/client style as a reference):

```python
@pytest.mark.asyncio
async def test_create_store_returns_nested_address(
    client: AsyncClient,
    seller_token: str,  # reuse the fixture name this file already uses for a seller JWT
) -> None:
    body = {"name": "Mini Mart", "address": make_address()}
    resp = await client.post(
        "/api/v1/stores/",
        json=body,
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["address"] == body["address"]


@pytest.mark.asyncio
async def test_create_store_rejects_missing_address_line1(
    client: AsyncClient, seller_token: str,
) -> None:
    body = {"name": "Mini Mart", "address": make_address(address_line1="")}
    resp = await client.post(
        "/api/v1/stores/",
        json=body,
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_store_by_id_returns_nested_address(
    client: AsyncClient, seller_token: str,
) -> None:
    body = {"name": "Mini Mart", "address": make_address()}
    create_resp = await client.post(
        "/api/v1/stores/",
        json=body,
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    store_id = create_resp.json()["id"]
    resp = await client.get(f"/api/v1/stores/{store_id}")
    assert resp.status_code == 200
    assert resp.json()["address"] == body["address"]
```

If the existing tests use different fixture names (e.g. a helper that creates a seller and issues a JWT inline), adapt the new tests to the same pattern rather than introducing a new fixture.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend/app && uv run pytest tests/test_stores.py -v`
Expected: failures in the create/get tests — the endpoint still accepts/returns a flat `Store` model.

- [ ] **Step 4: Create the store schemas**

```python
# backend/app/src/app/schemas/stores.py
"""Wire-format models for store endpoints."""

from pydantic import BaseModel

from app.schemas.address import AddressPayload


class StoreCreate(BaseModel):
    name: str
    address: AddressPayload


class StoreRead(BaseModel):
    id: int
    name: str
    address: AddressPayload
    is_active: bool
    seller_id: int
    created_at: str
    updated_at: str
```

- [ ] **Step 5: Update `stores.py` endpoints to use nested schemas**

In `backend/app/src/app/api/stores.py`, make these changes:

1. Add imports at the top:

```python
from app.schemas.address import address_from_payload, address_to_payload
from app.schemas.stores import StoreCreate, StoreRead
```

2. Replace `list_stores`, `list_my_stores`, `create_store`, and `get_store` with versions that read from the DB as `Store` rows but return `StoreRead`:

```python
def _store_read(store: Store) -> StoreRead:
    return StoreRead(
        id=store.id,
        name=store.name,
        address=address_to_payload(store),
        is_active=store.is_active,
        seller_id=store.seller_id,
        created_at=store.created_at.isoformat(),
        updated_at=store.updated_at.isoformat(),
    )


@router.get("/", response_model=List[StoreRead])
async def list_stores(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
) -> List[StoreRead]:
    result = await session.exec(
        select(Store).where(Store.is_active).offset(skip).limit(limit)
    )
    return [_store_read(store) for store in result.all()]


@router.get("/my", response_model=List[StoreRead])
async def list_my_stores(
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> List[StoreRead]:
    result = await session.exec(select(Store).where(Store.seller_id == seller.id))
    return [_store_read(store) for store in result.all()]


@router.post("/", response_model=StoreRead)
async def create_store(
    payload: StoreCreate,
    session: AsyncSession = Depends(get_db_session),
    seller: User = Depends(get_current_seller),
) -> StoreRead:
    assert seller.id is not None, "Seller ID cannot be None"
    store = Store(
        name=payload.name,
        seller_id=seller.id,
        **address_from_payload(payload.address),
    )
    session.add(store)
    await session.commit()
    await session.refresh(store)
    return _store_read(store)


@router.get("/{store_id}", response_model=StoreRead)
async def get_store(
    store_id: int, session: AsyncSession = Depends(get_db_session)
) -> StoreRead:
    store = await session.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return _store_read(store)
```

Leave the inventory endpoints unchanged.

- [ ] **Step 6: Run the test suite**

Run: `cd backend/app && uv run pytest tests/test_stores.py -v`
Expected: all tests (existing + new three) PASSED.

- [ ] **Step 7: Run the full backend test suite to check for collateral damage**

Run: `cd backend/app && uv run pytest -v`
Expected: all passes. Fix any remaining test that assumed a flat `address` string by swapping to `make_address()`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/src/app/schemas/stores.py backend/app/src/app/api/stores.py backend/app/tests/test_stores.py
git commit -m "feat(address): nest address payload on stores endpoints"
```

---

## Task 9: Lint & type-check gates (backend)

**Files:** (no changes expected — verification step)

- [ ] **Step 1: Run ruff**

Run: `cd backend/app && uv run ruff check .`
Expected: PASS.

- [ ] **Step 2: Run mypy**

Run: `cd backend/app && uv run mypy .`
Expected: PASS. If there are new type errors, fix them in place — do not add `# type: ignore` unless the existing codebase already used the same pattern.

- [ ] **Step 3: Run pytest one more time**

Run: `cd backend/app && uv run pytest -v`
Expected: all PASSED.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "chore(address): fix lint and type errors after structured-address split"
```

(Skip this step if no changes were needed.)

---

## Task 10: Frontend `Address` type and mock data

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/mock-data.ts`

- [ ] **Step 1: Update the types**

In `frontend/src/types/index.ts`, add an `Address` interface and change three existing fields. Open the file and:

1. Above the `Store` interface (around line 40), insert:

```typescript
/** Structured address matching backend AddressPayload. */
export interface Address {
  address_line1: string;
  address_line2: string | null;
  landmark: string | null;
  city: string;
  state: string;
  pincode: string;
  country: string;
  latitude: number | null;
  longitude: number | null;
}
```

2. Change `Store.address: string` to `address: Address`.
3. Change `SellerProfile.address: string` to `address: Address`.
4. Change `SellerApplication.address: string` to `address: Address`.

- [ ] **Step 2: Update `mock-data.ts` stores**

Replace the `mockStores` array in `frontend/src/lib/mock-data.ts` with:

```typescript
export const mockStores: Store[] = [
  {
    id: 1,
    name: "Sharma General Store",
    address: {
      address_line1: "12, MG Road",
      address_line2: "Sector 14",
      landmark: null,
      city: "Gurugram",
      state: "Haryana",
      pincode: "122001",
      country: "India",
      latitude: null,
      longitude: null,
    },
    is_active: true,
    seller_id: 1,
    created_at: "2026-02-01T06:00:00Z",
    updated_at: "2026-02-01T06:00:00Z",
  },
  {
    id: 2,
    name: "Krishna Supermart",
    address: {
      address_line1: "45, Nehru Nagar",
      address_line2: "Andheri West",
      landmark: null,
      city: "Mumbai",
      state: "Maharashtra",
      pincode: "400058",
      country: "India",
      latitude: null,
      longitude: null,
    },
    is_active: true,
    seller_id: 2,
    created_at: "2026-02-05T06:00:00Z",
    updated_at: "2026-02-05T06:00:00Z",
  },
  {
    id: 3,
    name: "Balaji Fresh Market",
    address: {
      address_line1: "78, Rajaji Street",
      address_line2: "T. Nagar",
      landmark: null,
      city: "Chennai",
      state: "Tamil Nadu",
      pincode: "600017",
      country: "India",
      latitude: null,
      longitude: null,
    },
    is_active: true,
    seller_id: 3,
    created_at: "2026-02-10T06:00:00Z",
    updated_at: "2026-02-10T06:00:00Z",
  },
];
```

- [ ] **Step 3: Check it compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: type errors in the call sites that still read `.address` as a string (signup, admin sellers, stores pages, home, sell). These are expected and will be fixed in the next tasks. Make sure `types/index.ts` and `mock-data.ts` themselves have no errors (filter the output to those paths).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/mock-data.ts
git commit -m "feat(address): add Address type and update mock stores"
```

---

## Task 11: Frontend `formatAddress` utility

**Files:**
- Create: `frontend/src/lib/format-address.ts`

- [ ] **Step 1: Implement the formatter**

```typescript
// frontend/src/lib/format-address.ts
import type { Address } from "@/types";

export function formatAddress(addr: Address): string {
  const parts: string[] = [addr.address_line1];
  if (addr.address_line2 && addr.address_line2.trim()) parts.push(addr.address_line2.trim());
  if (addr.landmark && addr.landmark.trim()) parts.push(addr.landmark.trim());
  parts.push(addr.city);
  parts.push(`${addr.state} ${addr.pincode}`);
  parts.push(addr.country);
  return parts.join(", ");
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/format-address.ts
git commit -m "feat(address): add formatAddress frontend utility"
```

---

## Task 12: Frontend `indian-states` fetch helper (cached)

**Files:**
- Create: `frontend/src/lib/indian-states.ts`

- [ ] **Step 1: Implement the cache**

```typescript
// frontend/src/lib/indian-states.ts
import { get } from "@/lib/api";

let cached: Promise<string[]> | null = null;

export function getIndianStates(): Promise<string[]> {
  if (cached) return cached;
  cached = get<{ states: string[] }>("/api/v1/meta/indian-states")
    .then((r) => r.states)
    .catch((err) => {
      cached = null; // retry on next call if the fetch failed
      throw err;
    });
  return cached;
}
```

Verify the signature of the `get` helper in `frontend/src/lib/api.ts` matches `<T>(url: string, token?: string) => Promise<T>`. If it differs, adapt the call above to the actual signature.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/indian-states.ts
git commit -m "feat(address): add cached indian-states fetch"
```

---

## Task 13: Frontend `AddressFields` shared component

**Files:**
- Create: `frontend/src/components/AddressFields.tsx`
- Create: `frontend/src/components/AddressFields.module.css`

- [ ] **Step 1: Implement the component**

```typescript
// frontend/src/components/AddressFields.tsx
"use client";

import { useEffect, useState } from "react";
import type { Address } from "@/types";
import { getIndianStates } from "@/lib/indian-states";
import styles from "./AddressFields.module.css";

export interface AddressFieldsErrors {
  address_line1?: string;
  address_line2?: string;
  landmark?: string;
  city?: string;
  state?: string;
  pincode?: string;
  country?: string;
  latitude?: string;
  longitude?: string;
}

export interface AddressFieldsProps {
  value: Address;
  onChange: (next: Address) => void;
  errors?: AddressFieldsErrors;
  disabled?: boolean;
}

export function emptyAddress(): Address {
  return {
    address_line1: "",
    address_line2: null,
    landmark: null,
    city: "",
    state: "",
    pincode: "",
    country: "India",
    latitude: null,
    longitude: null,
  };
}

export function AddressFields({ value, onChange, errors, disabled }: AddressFieldsProps) {
  const [states, setStates] = useState<string[]>([]);
  const [statesError, setStatesError] = useState<string | null>(null);

  useEffect(() => {
    getIndianStates()
      .then(setStates)
      .catch(() => setStatesError("Could not load states. Please refresh."));
  }, []);

  const update = <K extends keyof Address>(key: K, v: Address[K]) =>
    onChange({ ...value, [key]: v });

  const errClass = (k: keyof Address) =>
    errors?.[k] ? `${styles.input} ${styles.inputError}` : styles.input;

  return (
    <div className={styles.grid}>
      <div className={`${styles.field} ${styles.span2}`}>
        <label className={styles.label} htmlFor="addr-line1">Address line 1</label>
        <input
          id="addr-line1"
          type="text"
          className={errClass("address_line1")}
          value={value.address_line1}
          onChange={(e) => update("address_line1", e.target.value)}
          placeholder="House / building / street"
          maxLength={120}
          disabled={disabled}
          required
        />
        {errors?.address_line1 && <span className={styles.error}>{errors.address_line1}</span>}
      </div>

      <div className={`${styles.field} ${styles.span2}`}>
        <label className={styles.label} htmlFor="addr-line2">Address line 2 (optional)</label>
        <input
          id="addr-line2"
          type="text"
          className={errClass("address_line2")}
          value={value.address_line2 ?? ""}
          onChange={(e) => update("address_line2", e.target.value || null)}
          placeholder="Apartment / floor / unit"
          maxLength={120}
          disabled={disabled}
        />
      </div>

      <div className={`${styles.field} ${styles.span2}`}>
        <label className={styles.label} htmlFor="addr-landmark">Landmark (optional)</label>
        <input
          id="addr-landmark"
          type="text"
          className={errClass("landmark")}
          value={value.landmark ?? ""}
          onChange={(e) => update("landmark", e.target.value || null)}
          placeholder="Nearby reference"
          maxLength={120}
          disabled={disabled}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="addr-city">City / Town</label>
        <input
          id="addr-city"
          type="text"
          className={errClass("city")}
          value={value.city}
          onChange={(e) => update("city", e.target.value)}
          maxLength={80}
          disabled={disabled}
          required
        />
        {errors?.city && <span className={styles.error}>{errors.city}</span>}
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="addr-state">State</label>
        <select
          id="addr-state"
          className={errClass("state")}
          value={value.state}
          onChange={(e) => update("state", e.target.value)}
          disabled={disabled}
          required
        >
          <option value="">Select state</option>
          {states.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        {statesError && <span className={styles.error}>{statesError}</span>}
        {errors?.state && <span className={styles.error}>{errors.state}</span>}
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="addr-pincode">Pincode</label>
        <input
          id="addr-pincode"
          type="text"
          inputMode="numeric"
          pattern="[1-9]\d{5}"
          maxLength={6}
          className={errClass("pincode")}
          value={value.pincode}
          onChange={(e) => update("pincode", e.target.value.replace(/\D/g, "").slice(0, 6))}
          disabled={disabled}
          required
        />
        {errors?.pincode && <span className={styles.error}>{errors.pincode}</span>}
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="addr-country">Country</label>
        <input
          id="addr-country"
          type="text"
          className={errClass("country")}
          value={value.country}
          readOnly
          disabled
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add the stylesheet**

```css
/* frontend/src/components/AddressFields.module.css */
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.span2 {
  grid-column: 1 / -1;
}

.label {
  font-size: 0.85rem;
  color: var(--color-neutral-700);
  font-weight: 500;
}

.input {
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--color-neutral-300);
  border-radius: 6px;
  font: inherit;
  background: var(--color-bg-1);
}

.input:focus {
  outline: 2px solid var(--color-primary-500);
  outline-offset: -1px;
}

.inputError {
  border-color: var(--color-error-500);
}

.error {
  font-size: 0.8rem;
  color: var(--color-error-600);
}

@media (max-width: 640px) {
  .grid { grid-template-columns: 1fr; }
  .span2 { grid-column: 1; }
}
```

Before committing, open `frontend/src/styles/` (or wherever the design tokens live) and confirm the CSS custom properties referenced above (`--color-neutral-700`, `--color-neutral-300`, `--color-bg-1`, `--color-primary-500`, `--color-error-500`, `--color-error-600`) already exist. If one of them has a different name, substitute the actual token name.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AddressFields.tsx frontend/src/components/AddressFields.module.css
git commit -m "feat(address): add shared AddressFields component"
```

---

## Task 14: Seller signup wizard uses structured address

**Files:**
- Modify: `frontend/src/app/seller/signup/page.tsx`

- [ ] **Step 1: Replace `address: string` state with `address: Address`**

In `frontend/src/app/seller/signup/page.tsx`:

1. Add imports near the existing imports:

```typescript
import { AddressFields, emptyAddress } from "@/components/AddressFields";
import { formatAddress } from "@/lib/format-address";
import type { Address } from "@/types";
```

2. Replace:

```typescript
const [address, setAddress] = useState("");
```

with:

```typescript
const [address, setAddress] = useState<Address>(emptyAddress());
```

3. In the `resubmit` `useEffect` that calls `get<SellerProfile>(...)`, replace:

```typescript
setAddress(profile.address);
```

with the same line — it already assigns an `Address` now that the type was updated. No change needed here aside from confirming the compiler is happy.

- [ ] **Step 2: Replace the step-4 address input with `<AddressFields>`**

Locate the JSX block that currently renders the address input inside step 4 (the `<div className={`${styles.inputGroup} ${styles.formGridFull}`}>` containing the `<label htmlFor="address">`, single `<input id="address">`, and the inline error). Replace that entire block with:

```typescript
<div className={`${styles.inputGroup} ${styles.formGridFull}`}>
  <label className={styles.label}>Business address</label>
  <AddressFields
    value={address}
    onChange={setAddress}
    errors={{
      address_line1: fieldErrors.address_line1,
      city: fieldErrors.city,
      state: fieldErrors.state,
      pincode: fieldErrors.pincode,
    }}
  />
</div>
```

- [ ] **Step 3: Update the step-4 Next button validation**

Find the step-4 Next button's onClick handler with the `errs` object and the check `if (!address.trim()) errs.address = "Address is required";`. Replace that single line with:

```typescript
if (!address.address_line1.trim()) errs.address_line1 = "Address line 1 is required";
if (!address.city.trim()) errs.city = "City is required";
if (!address.state) errs.state = "State is required";
if (!/^[1-9]\d{5}$/.test(address.pincode)) errs.pincode = "Enter a valid 6-digit pincode";
```

- [ ] **Step 4: Update the step-6 review row**

Replace:

```typescript
<div className={styles.reviewRow}>
  <span className={styles.reviewLabel}>Address</span>
  <span className={styles.reviewValue}>{address}</span>
</div>
```

with:

```typescript
<div className={styles.reviewRow}>
  <span className={styles.reviewLabel}>Address</span>
  <span className={styles.reviewValue}>{formatAddress(address)}</span>
</div>
```

- [ ] **Step 5: Update the register + patch bodies**

In `handleSubmit`:

1. In the `isResubmit` branch's `patch(...)` body, replace the line `address,` with `address,` — but verify the field is still named `address`. Because the key is already `address` and the value is now the `Address` object, the patch body needs no change beyond type-correctness.

2. In the register branch's `post("/api/v1/auth/seller/register", {...})` body, the `address,` line similarly stays as is. The backend now expects a nested object.

(No textual edit is actually needed in `handleSubmit` itself — this step's purpose is just to confirm no flat-string assumption remains.)

- [ ] **Step 6: Type-check and smoke-test**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS for `app/seller/signup/page.tsx`.

Run: `cd frontend && npm run lint`
Expected: PASS.

Manual smoke test:

1. Start backend (`cd backend/app && uv run uvicorn app.main:app --reload`) and frontend (`cd frontend && npm run dev`).
2. Visit `http://localhost:3000/seller/signup`, complete the flow with a valid structured address, confirm the review step shows a formatted single-line string, confirm the submit succeeds and lands on `/seller/signup/pending`.
3. Try submitting with pincode `12345` on step 4 — Next should block with an inline error.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/seller/signup/page.tsx
git commit -m "feat(address): seller signup wizard uses structured address"
```

---

## Task 15: Admin sellers review modal renders structured block

**Files:**
- Modify: `frontend/src/app/admin/sellers/page.tsx`

- [ ] **Step 1: Replace the single address row**

Around line 311-314 of `frontend/src/app/admin/sellers/page.tsx`, locate:

```typescript
<div className={styles.detailsRow}>
  <span className={styles.detailsLabel}>Address</span>
  <span className={styles.detailsValue}>{reviewing.address}</span>
</div>
```

Replace with:

```typescript
<div className={styles.detailsRow}>
  <span className={styles.detailsLabel}>Address line 1</span>
  <span className={styles.detailsValue}>{reviewing.address.address_line1}</span>
</div>
{reviewing.address.address_line2 && (
  <div className={styles.detailsRow}>
    <span className={styles.detailsLabel}>Address line 2</span>
    <span className={styles.detailsValue}>{reviewing.address.address_line2}</span>
  </div>
)}
{reviewing.address.landmark && (
  <div className={styles.detailsRow}>
    <span className={styles.detailsLabel}>Landmark</span>
    <span className={styles.detailsValue}>{reviewing.address.landmark}</span>
  </div>
)}
<div className={styles.detailsRow}>
  <span className={styles.detailsLabel}>City</span>
  <span className={styles.detailsValue}>{reviewing.address.city}</span>
</div>
<div className={styles.detailsRow}>
  <span className={styles.detailsLabel}>State</span>
  <span className={styles.detailsValue}>{reviewing.address.state}</span>
</div>
<div className={styles.detailsRow}>
  <span className={styles.detailsLabel}>Pincode</span>
  <span className={styles.detailsValue}>{reviewing.address.pincode}</span>
</div>
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors in `admin/sellers/page.tsx`.

- [ ] **Step 3: Smoke-test**

Log in as admin, open the seller review modal for a recently signed-up seller (after Task 14), and confirm each address row renders its own value.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/admin/sellers/page.tsx
git commit -m "feat(address): admin seller review modal shows structured address block"
```

---

## Task 16: Stores pages render `formatAddress(store.address)`

**Files:**
- Modify: `frontend/src/app/stores/page.tsx`
- Modify: `frontend/src/app/stores/[id]/page.tsx`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/sell/page.tsx`

- [ ] **Step 1: Update each file**

In each of the four files above, search for `.address}` (or similar) where a store's address is rendered as a string. Replace every such expression with `formatAddress(<owner>.address)` and add the import `import { formatAddress } from "@/lib/format-address";` near the top of the file.

Concretely, use this command to list every call site first:

```bash
grep -n "store.address\|\.address}\|\.address\b" frontend/src/app/stores/page.tsx frontend/src/app/stores/\[id\]/page.tsx frontend/src/app/page.tsx frontend/src/app/sell/page.tsx
```

For each hit where the surrounding JSX renders a string directly from `.address`, swap it to `formatAddress(<owner>.address)`. Skip any hits where `.address` is something else (e.g. email address, `addressline1` already-flat reference).

- [ ] **Step 2: Type-check and lint**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

Run: `cd frontend && npm run lint`
Expected: PASS.

- [ ] **Step 3: Smoke-test**

Visit `/stores`, `/stores/1`, `/`, and `/sell` (or whatever the sell page route is). Confirm that each rendered store address reads as a single-line string like `12, MG Road, Sector 14, Gurugram, Haryana 122001, India`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/stores/page.tsx "frontend/src/app/stores/[id]/page.tsx" frontend/src/app/page.tsx frontend/src/app/sell/page.tsx
git commit -m "feat(address): render formatted address on store-facing pages"
```

---

## Task 17: Frontend quality gates

**Files:** (no changes expected — verification)

- [ ] **Step 1: Run ESLint**

Run: `cd frontend && npm run lint`
Expected: PASS.

- [ ] **Step 2: Run the production build**

Run: `cd frontend && npm run build`
Expected: PASS. Type errors surfaced here must be fixed before moving on.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "chore(address): frontend lint and build fixes"
```

(Skip if no changes were needed.)

---

## Task 18: End-to-end manual smoke test

**Files:** (no changes expected)

- [ ] **Step 1: Reset dev data**

Run: `cd backend/app && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: migration cleanly rolls back and re-applies.

- [ ] **Step 2: Start the full stack**

Run (separate terminals):

```bash
docker-compose up -d
cd backend/app && uv run uvicorn app.main:app --reload
cd frontend && npm run dev
```

- [ ] **Step 3: Walk the happy path**

1. Visit `http://localhost:3000/seller/signup`.
2. Enter email, get OTP from backend logs (or `EMAIL_PROVIDER=console`).
3. Complete steps 3–5 with a structured address: line1 `12 MG Road`, line2 `Sector 14`, landmark `Near Cyber Hub`, city `Gurugram`, state `Haryana` (selected from dropdown), pincode `122001`.
4. Review step shows `12 MG Road, Sector 14, Near Cyber Hub, Gurugram, Haryana 122001, India`.
5. Submit. Land on `/seller/signup/pending`.
6. As an admin (separate login), visit `/admin/sellers`, open the new applicant's review modal, confirm structured block renders.

- [ ] **Step 4: Walk the failure path**

1. Try signup with pincode `12345` → Next blocked.
2. Try signup with pincode `023456` → Next blocked (leading zero).
3. Try signup leaving state empty → Next blocked.

- [ ] **Step 5: No commit — this is a verification step**

If anything fails, fix the underlying task before this one.

---

## Self-Review

- **Spec coverage:**
  - Field schema (9 fields, validators): Task 2, Task 4.
  - `AddressBase` mixin on `SellerProfile` + `Store`: Task 4.
  - `format_address` helper: Task 3 (backend), Task 11 (frontend).
  - `GET /meta/indian-states`: Task 6.
  - Nested `address` on `/auth/seller/register`, `/sellers/me/profile`, admin applications: Task 7.
  - Nested `address` on stores endpoints: Task 8.
  - Migration (truncate + drop + add): Task 5.
  - Frontend `Address` type + `AddressFields` component + cached states fetch: Tasks 10, 12, 13.
  - Seller signup wizard: Task 14.
  - Admin review modal: Task 15.
  - Store-facing display via `formatAddress`: Task 16.
  - Mock data: Task 10.
  - Backend unit + endpoint tests: Tasks 1, 2, 3, 6, 7, 8.
  - Manual frontend test plan: Task 18.

- **Placeholder scan:** No TBDs, TODOs, or "similar to Task N" shortcuts. Every code step contains concrete content.

- **Type consistency:**
  - `Address` / `AddressPayload` / `AddressBase` all use identical field names: `address_line1`, `address_line2`, `landmark`, `city`, `state`, `pincode`, `country`, `latitude`, `longitude`.
  - `address_from_payload` / `address_to_payload` used consistently in every API handler that crosses the boundary.
  - `formatAddress` signature matches the backend's `format_address` output shape for a 1:1 parity so admins comparing logs to UI see the same string.
  - Alembic `ADDRESS_COLUMNS_REQUIRED` / `ADDRESS_COLUMNS_OPTIONAL` sets sum to 9 and match the mixin's nullability.

- **Scope:** One spec, one migration, one PR. No unrelated refactors.
