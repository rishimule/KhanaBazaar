# Seller Services & 1-Store-Per-Seller Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the free-text `SellerProfile.business_category` with a many-to-many SellerProfile↔Service link, capture services during seller signup, and auto-provision a single Store per seller on admin approval.

**Architecture:** New `sellerprofile_service` junction table holds the link. `business_category` column is dropped. `store.seller_profile_id` becomes UNIQUE. Existing `PATCH /sellers/admin/{id}/verify` endpoint augmented to auto-create the Store (deep-copying business address) on `approve`. All seller flows (register, me/profile GET+PATCH, admin applications) gain a `services`/`service_ids` field. Signup wizard step 4 swaps the free-text input for a multi-select checkbox grid. Admin sellers UI swaps the category badge for service badges and adds an inline edit popover.

**Tech Stack:** FastAPI, SQLModel + Alembic, Postgres (asyncpg), Pydantic v2, Pytest + pytest-asyncio, Next.js 15 (App Router), TypeScript, CSS Modules.

**Reference spec:** `docs/superpowers/specs/2026-05-03-seller-services-design.md`

**Working directory note:** All `uv` commands run from `backend/app/`. All `npm`/`npx` commands run from `frontend/`. All `git` commands from repo root.

**Branch:** Continue work on `docs/seller-services-spec` (or rebase onto a fresh `feat/seller-services` branch — see Task 0).

---

## Task 0: Branch setup

**Files:** none (git only)

- [ ] **Step 1: Create implementation branch from main**

```bash
git checkout main
git pull origin main
git checkout -b feat/seller-services
git cherry-pick docs/seller-services-spec  # bring in spec commit
```

If the catalog work from the prior session is needed (`backend/app/src/app/api/catalog.py`, `backend/app/src/app/db/dev_seed.py`, frontend types/admin/categories changes, `backend/app/tests/test_catalog.py`), commit those separately first on their own branch (`feat/catalog-services-endpoint`) and rebase this branch on top of that. They are prerequisites — `GET /catalog/services` is consumed by the signup wizard.

- [ ] **Step 2: Verify clean working tree**

Run: `git status`
Expected: only the spec file present from the cherry-pick, otherwise clean.

---

## Task 1: Add `SellerProfileService` model

**Files:**
- Modify: `backend/app/src/app/models/profile.py`
- Modify: `backend/app/src/app/models/__init__.py`

- [ ] **Step 1: Append the model to `profile.py`**

Add at the bottom of `backend/app/src/app/models/profile.py`:

```python
class SellerProfileService(BaseSchema, table=True):
    __tablename__ = "sellerprofile_service"
    __table_args__ = (
        UniqueConstraint(
            "seller_profile_id", "service_id", name="uq_sellerprofile_service"
        ),
    )
    seller_profile_id: int = Field(
        foreign_key="sellerprofile.id", nullable=False, index=True
    )
    service_id: int = Field(
        foreign_key="service.id", nullable=False, index=True
    )
```

- [ ] **Step 2: Export from `models/__init__.py`**

In `backend/app/src/app/models/__init__.py`, add `SellerProfileService` to the imports from `app.models.profile` and to `__all__`.

- [ ] **Step 3: Run the schema-registration test to verify the table appears**

Run: `uv run pytest tests/test_schema_reset_models.py -v`
Expected: existing tests still PASS. The new model is loaded into metadata even if no test asserts it yet.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/models/profile.py backend/app/src/app/models/__init__.py
git commit -m "feat(sellers): add SellerProfileService junction model"
```

---

## Task 2: Update schema-reset assertion

**Files:**
- Modify: `backend/app/tests/test_schema_reset_models.py`

- [ ] **Step 1: Add `sellerprofile_service` to expected tables and import**

In `tests/test_schema_reset_models.py`:
- Add import: `from app.models.profile import SellerProfileService` (alongside other profile imports)
- Add `"sellerprofile_service"` to the `expected` set in `test_expected_tables_are_registered_in_metadata`
- Add `SellerProfileService` to the `classes` list in `test_model_classes_are_imported`

- [ ] **Step 2: Add a column-presence test**

Append to the same file:

```python
def test_sellerprofile_service_columns_are_present() -> None:
    cols = {column.name for column in inspect(SellerProfileService).columns}
    assert {"id", "seller_profile_id", "service_id", "created_at", "updated_at"}.issubset(cols)
```

- [ ] **Step 3: Run the file**

Run: `uv run pytest tests/test_schema_reset_models.py -v`
Expected: all PASS including the new column test.

- [ ] **Step 4: Commit**

```bash
git add backend/app/tests/test_schema_reset_models.py
git commit -m "test(sellers): assert SellerProfileService is registered"
```

---

## Task 3: Generate the Alembic migration skeleton

**Files:**
- Create: `backend/app/migrations/versions/<rev>_seller_services.py`

- [ ] **Step 1: Auto-generate migration**

Run from `backend/app/`:

```bash
uv run alembic revision --autogenerate -m "add seller services drop business_category"
```

Note the generated revision id (e.g. `4f2c81e9d3a8`). The migration file will be created under `migrations/versions/`.

- [ ] **Step 2: Open the generated file and verify it includes**

- `op.create_table("sellerprofile_service", ...)`
- `op.create_index(...)` for the two FK columns
- `op.create_unique_constraint("uq_sellerprofile_service", "sellerprofile_service", ["seller_profile_id", "service_id"])`
- `op.drop_column("sellerprofile", "business_category")`

If any of those are missing, add them by hand using existing migration files as template.

- [ ] **Step 3: Do NOT yet add data backfill or store unique constraint**

Those go in Task 4. Keep this commit focused on the auto-generated structure only.

- [ ] **Step 4: Commit**

```bash
git add backend/app/migrations/versions/<rev>_seller_services.py
git commit -m "chore(migrations): scaffold seller services migration"
```

---

## Task 4: Hand-edit migration — backfill and store unique constraint

**Files:**
- Modify: the migration file from Task 3

- [ ] **Step 1: In `upgrade()`, replace the auto-generated body with this exact ordering**

```python
def upgrade() -> None:
    # 1. Create junction table
    op.create_table(
        "sellerprofile_service",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seller_profile_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["seller_profile_id"], ["sellerprofile.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["service.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "seller_profile_id", "service_id", name="uq_sellerprofile_service"
        ),
    )
    op.create_index(
        op.f("ix_sellerprofile_service_seller_profile_id"),
        "sellerprofile_service",
        ["seller_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sellerprofile_service_service_id"),
        "sellerprofile_service",
        ["service_id"],
        unique=False,
    )

    # 2. Backfill: every existing seller profile gets the grocery service.
    #    Skip if grocery service does not exist (clean DB before seed).
    op.execute(
        """
        INSERT INTO sellerprofile_service (created_at, updated_at, seller_profile_id, service_id)
        SELECT NOW(), NOW(), sp.id, s.id
        FROM sellerprofile sp
        CROSS JOIN service s
        WHERE s.slug = 'grocery'
        ON CONFLICT (seller_profile_id, service_id) DO NOTHING
        """
    )

    # 3. Drop business_category
    op.drop_column("sellerprofile", "business_category")

    # 4. Enforce 1 store per seller
    op.create_unique_constraint(
        "uq_store_seller_profile", "store", ["seller_profile_id"]
    )
```

- [ ] **Step 2: Replace `downgrade()` with**

```python
def downgrade() -> None:
    op.drop_constraint("uq_store_seller_profile", "store", type_="unique")
    op.add_column(
        "sellerprofile",
        sa.Column("business_category", sa.String(), nullable=True),
    )
    op.execute(
        "UPDATE sellerprofile SET business_category = 'Groceries' WHERE business_category IS NULL"
    )
    op.alter_column("sellerprofile", "business_category", nullable=False)
    op.drop_index(
        op.f("ix_sellerprofile_service_service_id"), table_name="sellerprofile_service"
    )
    op.drop_index(
        op.f("ix_sellerprofile_service_seller_profile_id"),
        table_name="sellerprofile_service",
    )
    op.drop_table("sellerprofile_service")
```

- [ ] **Step 3: Apply migration to the dev database**

```bash
uv run alembic upgrade head
```

Expected: success, no errors.

- [ ] **Step 4: Verify in psql or via inline script**

```bash
uv run python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings
async def main():
    e = create_async_engine(settings.DATABASE_URL)
    async with e.connect() as c:
        r = await c.execute(text(
            \"SELECT column_name FROM information_schema.columns WHERE table_name='sellerprofile' AND column_name='business_category'\"
        ))
        assert list(r) == [], 'business_category still present'
        r = await c.execute(text('SELECT count(*) FROM sellerprofile_service'))
        print('junction rows:', list(r))
    await e.dispose()
asyncio.run(main())
"
```

Expected: `junction rows: [(N,)]` where N matches existing sellerprofile rows (or `[(0,)]` on a fresh DB).

- [ ] **Step 5: Commit**

```bash
git add backend/app/migrations/versions/<rev>_seller_services.py
git commit -m "feat(migrations): backfill grocery, drop business_category, unique store-per-seller"
```

---

## Task 5: Update dev seed data — schema

**Files:**
- Modify: `backend/app/src/app/db/dev_seed.py`

- [ ] **Step 1: Replace `business_category` with `service_slugs` in seed dictionaries**

In `dev_seed.py`:

- For every `APPLICATIONS` entry, remove the `"business_category": "..."` key and add `"service_slugs": ["grocery"]`.
- For every `STORE_OWNER_PROFILES` entry, do the same. (Existing values "Groceries", "Organic Produce", "Fresh Produce" all map to the single `grocery` service.)

- [ ] **Step 2: Update `_upsert_seller_profile` to upsert junction rows**

Add this helper above `_upsert_seller_profile`:

```python
async def _upsert_seller_profile_services(
    session: AsyncSession, profile: SellerProfile, service_slugs: list[str]
) -> None:
    from app.models.profile import SellerProfileService

    assert profile.id is not None
    service_ids: list[int] = []
    for slug in service_slugs:
        result = await session.exec(select(Service).where(Service.slug == slug))
        service = result.first()
        assert service is not None and service.id is not None, (
            f"seed expected service with slug={slug!r}; ensure SERVICES are seeded first"
        )
        service_ids.append(service.id)

    existing_result = await session.exec(
        select(SellerProfileService).where(
            SellerProfileService.seller_profile_id == profile.id
        )
    )
    existing = {row.service_id: row for row in existing_result.all()}
    desired = set(service_ids)

    for service_id in desired - existing.keys():
        session.add(
            SellerProfileService(seller_profile_id=profile.id, service_id=service_id)
        )
    for service_id, row in existing.items():
        if service_id not in desired:
            await session.delete(row)
    await session.flush()
```

Add `from app.models.profile import SellerProfileService` to the file's imports at the top.

- [ ] **Step 3: Drop `business_category` from `_upsert_seller_profile`**

In `_upsert_seller_profile`, remove the `business_category=data["business_category"]` arg from the `SellerProfile(...)` constructor and remove `profile.business_category = data["business_category"]` from the update path. After the existing `await session.flush()` at the end of the function, call:

```python
    await _upsert_seller_profile_services(session, profile, data["service_slugs"])
```

- [ ] **Step 4: Reorder `seed_demo_data` so services exist before profiles**

In `seed_demo_data`, ensure `_ensure_service` is called for every entry in `SERVICES` BEFORE any call to `_upsert_seller_profile` (it currently runs after profile creation). Move the `services_by_slug` block above the `for profile_data in STORE_OWNER_PROFILES:` loop.

Also make `seed_seller_application_subset` seed the services first (call the existing `services_by_slug` loop) — the function currently only seeds languages, admin, and applications.

- [ ] **Step 5: Update `EXPECTED_FULL_COUNTS`**

Add `"sellerprofile_service": 6,` to the dictionary (one row per seller × one service each).

- [ ] **Step 6: Update `_COUNT_MODELS`**

Add the entry: `"sellerprofile_service": SellerProfileService,`

- [ ] **Step 7: Run dev_seed tests**

Run: `uv run pytest tests/test_dev_seed.py -v`
Expected: all PASS.

- [ ] **Step 8: Re-seed local DB end-to-end**

```bash
uv run python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings
async def main():
    e = create_async_engine(settings.DATABASE_URL)
    async with e.begin() as c:
        await c.execute(text('DROP SCHEMA public CASCADE'))
        await c.execute(text('CREATE SCHEMA public'))
    await e.dispose()
asyncio.run(main())
"
uv run alembic upgrade head
uv run python scripts/seed_database.py
```

Expected: `Verified counts:` block lists `sellerprofile_service: 6` and all other counts match.

- [ ] **Step 9: Commit**

```bash
git add backend/app/src/app/db/dev_seed.py
git commit -m "feat(seed): replace business_category with service_slugs"
```

---

## Task 6: Update API schemas

**Files:**
- Modify: `backend/app/src/app/schemas/sellers.py`
- Create (optional): `backend/app/src/app/schemas/services.py` (or reuse existing types from `app.api.catalog`)

- [ ] **Step 1: Reuse `ServiceRead` from the catalog API**

`app/api/catalog.py` already defines `ServiceRead` with `id/created_at/updated_at/slug/name/description/is_active/sort_order`. Re-export from a neutral module so seller schemas don't import from API layer:

Create `backend/app/src/app/schemas/services.py`:

```python
"""Wire-format model for services. Mirrors the shape returned by
GET /catalog/services so frontend code can reuse a single Service type."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ServicePayload(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    slug: str
    name: str
    description: Optional[str] = None
    is_active: bool
    sort_order: int
```

Update `app/api/catalog.py` to import `ServicePayload` from `app.schemas.services` and alias `ServiceRead = ServicePayload` (keep the local name to avoid touching every existing reference). Frontend keeps using its existing `Service` interface.

- [ ] **Step 2: Update each schema to add `services` / `service_ids` and drop `business_category`**

Edit `backend/app/src/app/schemas/sellers.py`:

```python
class SellerRegisterBody(BaseModel):
    email_token: str
    full_name: str
    phone: str
    business_name: str
    service_ids: list[int] = Field(min_length=1)
    address: AddressPayload
    gst_number: Optional[str] = None
    fssai_license: Optional[str] = None
    bank_account_number: str
    bank_ifsc: str


class SellerProfileUpdateBody(BaseModel):
    full_name: Optional[str] = None
    business_name: str
    service_ids: Optional[list[int]] = Field(default=None, min_length=1)
    address: AddressPayload
    phone: str
    gst_number: Optional[str] = None
    fssai_license: Optional[str] = None
    bank_account_number: str
    bank_ifsc: str


class SellerProfilePayload(BaseModel):
    id: int
    user_id: int
    full_name: str
    business_name: str
    services: list["ServicePayload"]
    address: AddressPayload
    phone: str
    gst_number: Optional[str] = None
    fssai_license: Optional[str] = None
    bank_account_number: str
    bank_ifsc: str
    verification_status: str
    rejection_reason: Optional[str] = None


class SellerApplicationPayload(BaseModel):
    seller_id: int
    email: EmailStr
    full_name: Optional[str] = None
    business_name: str
    services: list["ServicePayload"]
    address: AddressPayload
    phone: str
    gst_number: Optional[str] = None
    fssai_license: Optional[str] = None
    bank_account_number: str
    bank_ifsc: str
    verification_status: str
    rejection_reason: Optional[str] = None
    submitted_at: Optional[str] = None
    updated_at: Optional[str] = None


class AdminSetServicesBody(BaseModel):
    service_ids: list[int] = Field(min_length=1)
```

Add to imports:
```python
from pydantic import BaseModel, EmailStr, Field
from app.schemas.services import ServicePayload
```

Drop the inline forward references (the `"ServicePayload"` string quotes used above) — replace with the imported `ServicePayload` directly.

- [ ] **Step 3: Type-check**

Run: `uv run mypy src/app/schemas/sellers.py`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/schemas/sellers.py
git commit -m "feat(schemas): add services to seller payloads, drop business_category"
```

---

## Task 7: Helper — fetch profile services and validate service_ids

**Files:**
- Create: `backend/app/src/app/services/seller_services.py`

- [ ] **Step 1: Create the helper module**

```python
"""Helpers for managing seller↔service junction rows and validating
incoming service_id payloads."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Service, ServiceTranslation
from app.models.profile import SellerProfile, SellerProfileService
from app.schemas.sellers import ServicePayload


async def validate_service_ids(
    session: AsyncSession, service_ids: list[int]
) -> list[int]:
    """Return deduped, ordered list of valid active service ids.

    Raises ValueError if any id is missing or inactive.
    """
    deduped = list(dict.fromkeys(service_ids))  # preserve order, drop dupes
    if not deduped:
        raise ValueError("service_ids must not be empty")
    result = await session.exec(
        select(Service.id).where(
            Service.id.in_(deduped),  # type: ignore[union-attr]
            Service.is_active == True,  # noqa: E712
        )
    )
    found = set(result.all())
    missing = [sid for sid in deduped if sid not in found]
    if missing:
        raise ValueError(f"unknown or inactive service_ids: {missing}")
    return deduped


async def replace_profile_services(
    session: AsyncSession, profile: SellerProfile, service_ids: list[int]
) -> None:
    """Replace a seller's service set atomically. Caller commits."""
    assert profile.id is not None
    existing_result = await session.exec(
        select(SellerProfileService).where(
            SellerProfileService.seller_profile_id == profile.id
        )
    )
    existing = {row.service_id: row for row in existing_result.all()}
    desired = set(service_ids)

    for service_id in desired - existing.keys():
        session.add(
            SellerProfileService(
                seller_profile_id=profile.id, service_id=service_id
            )
        )
    for service_id, row in list(existing.items()):
        if service_id not in desired:
            await session.delete(row)
    await session.flush()


async def list_profile_services(
    session: AsyncSession, seller_profile_id: int, language_code: str = "en"
) -> list[ServicePayload]:
    """Resolve a seller's services with English translation, ordered by Service.sort_order."""
    stmt = (
        select(Service, ServiceTranslation)
        .join(
            SellerProfileService,
            SellerProfileService.service_id == Service.id,  # type: ignore[arg-type]
        )
        .join(
            ServiceTranslation,
            ServiceTranslation.service_id == Service.id,  # type: ignore[arg-type]
            isouter=True,
        )
        .where(SellerProfileService.seller_profile_id == seller_profile_id)
        .where(
            (ServiceTranslation.language_code == language_code)
            | (ServiceTranslation.id.is_(None))  # type: ignore[union-attr]
        )
        .order_by(Service.sort_order, Service.id)  # type: ignore[arg-type]
    )
    result = await session.exec(stmt)
    payloads: list[ServicePayload] = []
    for service, translation in result.all():
        assert service.id is not None
        payloads.append(
            ServicePayload(
                id=service.id,
                slug=service.slug,
                name=translation.name if translation else service.slug,
            )
        )
    return payloads
```

- [ ] **Step 2: Type-check**

Run: `uv run mypy src/app/services/seller_services.py`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/app/src/app/services/seller_services.py
git commit -m "feat(sellers): add service_ids validation + junction helpers"
```

---

## Task 8: Wire `service_ids` into `POST /auth/seller/register`

**Files:**
- Modify: `backend/app/src/app/api/auth.py:175-218`
- Modify: `backend/app/tests/test_seller_register.py`

- [ ] **Step 1: Write a failing test for empty service_ids**

In `tests/test_seller_register.py`, add:

```python
@pytest.mark.asyncio
async def test_register_rejects_empty_service_ids(
    client: AsyncClient, valid_email_token: str
) -> None:
    payload = _valid_register_payload(email_token=valid_email_token, service_ids=[])
    resp = await client.post("/api/v1/auth/seller/register", json=payload)
    assert resp.status_code == 422
```

If `_valid_register_payload` doesn't already exist, add a small builder near the top of the test file — the file already constructs registration payloads; replace the inline `business_category: "..."` calls with `service_ids` lists. Use the seeded grocery service id from a `seeded_grocery_service_id` fixture defined as:

```python
@pytest.fixture
async def seeded_grocery_service_id(session: AsyncSession) -> int:
    from app.models.catalog import Service, ServiceTranslation
    service = Service(slug="grocery", is_active=True, sort_order=0)
    session.add(service)
    await session.flush()
    session.add(ServiceTranslation(service_id=service.id, language_code="en", name="Grocery"))
    await session.flush()
    sid = service.id
    await session.commit()
    return sid
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_seller_register.py::test_register_rejects_empty_service_ids -v`
Expected: FAIL (current schema still uses `business_category`).

- [ ] **Step 3: Update the registration handler**

In `backend/app/src/app/api/auth.py`, replace the `seller_register` body roughly with:

```python
@router.post("/seller/register")
async def seller_register(
    body: SellerRegisterBody,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.services.seller_services import (
        replace_profile_services,
        validate_service_ids,
    )

    email = decode_email_verification_token(body.email_token)

    result = await session.exec(select(User).where(User.email == email))
    if result.first():
        raise HTTPException(status_code=409, detail={"error": "email_already_registered"})

    try:
        valid_ids = await validate_service_ids(session, body.service_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        phone=body.phone,
        gst_number=body.gst_number,
        fssai_license=body.fssai_license,
        bank_account_number=body.bank_account_number,
        bank_ifsc=body.bank_ifsc,
        business_address_id=address.id,
    )
    session.add(profile)
    await session.flush()
    await replace_profile_services(session, profile, valid_ids)

    await session.commit()
    await session.refresh(user)

    token = create_access_token(user)
    full_name = compose_full_name(first_name, last_name)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _user_payload(user, full_name),
    }
```

- [ ] **Step 4: Add a happy-path test**

```python
@pytest.mark.asyncio
async def test_register_persists_services(
    client: AsyncClient,
    session: AsyncSession,
    valid_email_token: str,
    seeded_grocery_service_id: int,
) -> None:
    payload = _valid_register_payload(
        email_token=valid_email_token, service_ids=[seeded_grocery_service_id]
    )
    resp = await client.post("/api/v1/auth/seller/register", json=payload)
    assert resp.status_code == 200, resp.text
    from app.models.profile import SellerProfile, SellerProfileService
    profile = (await session.exec(select(SellerProfile))).first()
    assert profile is not None
    rows = (
        await session.exec(
            select(SellerProfileService).where(
                SellerProfileService.seller_profile_id == profile.id
            )
        )
    ).all()
    assert {r.service_id for r in rows} == {seeded_grocery_service_id}
```

- [ ] **Step 5: Add an invalid-id test**

```python
@pytest.mark.asyncio
async def test_register_rejects_unknown_service_id(
    client: AsyncClient, valid_email_token: str
) -> None:
    payload = _valid_register_payload(email_token=valid_email_token, service_ids=[99999])
    resp = await client.post("/api/v1/auth/seller/register", json=payload)
    assert resp.status_code == 400
    assert "service_ids" in resp.json()["detail"]
```

- [ ] **Step 6: Run all three new tests**

Run: `uv run pytest tests/test_seller_register.py -v`
Expected: all PASS, including the existing tests after their `business_category` references are removed.

- [ ] **Step 7: Audit existing tests in this file** — find every `business_category=` literal and switch to `service_ids=[seeded_grocery_service_id]` using the new fixture. Add the fixture to `conftest.py` if used in multiple files.

- [ ] **Step 8: Commit**

```bash
git add backend/app/src/app/api/auth.py backend/app/tests/test_seller_register.py
git commit -m "feat(auth): seller register accepts service_ids"
```

---

## Task 9: GET `/sellers/me/profile` returns `services`

**Files:**
- Modify: `backend/app/src/app/api/sellers.py:55-78`
- Modify: existing seller-me test (find with `grep -n "me/profile" backend/app/tests`)

- [ ] **Step 1: Write a failing test asserting `services` array**

Add to whichever test file already exercises `/sellers/me/profile` (likely `test_seller_status.py` or a new `test_seller_me.py`):

```python
@pytest.mark.asyncio
async def test_get_me_profile_returns_services(
    client: AsyncClient, override_as_seller_with_grocery: None
) -> None:
    resp = await client.get("/api/v1/sellers/me/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert "business_category" not in body
    assert "services" in body
    assert isinstance(body["services"], list)
    assert body["services"][0]["slug"] == "grocery"
```

The `override_as_seller_with_grocery` fixture seeds a seller profile + one junction row. Build it from existing patterns in `test_carts.py`'s `seed` fixture.

- [ ] **Step 2: Update `get_seller_profile` handler**

```python
@router.get("/me/profile", response_model=SellerProfilePayload)
async def get_seller_profile(
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> SellerProfilePayload:
    from app.services.seller_services import list_profile_services

    assert current_user.id is not None
    profile = await _seller_profile_with_address(session, current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    services = await list_profile_services(session, profile.id)
    return SellerProfilePayload(
        id=profile.id,
        user_id=profile.user_id,
        full_name=compose_full_name(profile.first_name, profile.last_name),
        business_name=profile.business_name,
        services=services,
        address=address_to_payload(profile.business_address),
        phone=profile.phone,
        gst_number=profile.gst_number,
        fssai_license=profile.fssai_license,
        bank_account_number=profile.bank_account_number,
        bank_ifsc=profile.bank_ifsc,
        verification_status=profile.verification_status.value,
        rejection_reason=profile.rejection_reason,
    )
```

- [ ] **Step 3: Run**

Run: `uv run pytest tests/test_seller_status.py tests/test_seller_register.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/api/sellers.py backend/app/tests/test_seller_status.py
git commit -m "feat(sellers): GET /me/profile exposes services"
```

---

## Task 10: PATCH `/sellers/me/profile` services rules

**Files:**
- Modify: `backend/app/src/app/api/sellers.py:81-116`

- [ ] **Step 1: Write three tests**

Append to `tests/test_seller_status.py` (or wherever PATCH tests live):

```python
@pytest.mark.asyncio
async def test_patch_me_pending_can_change_services(
    client: AsyncClient,
    session: AsyncSession,
    override_as_seller_pending: None,
    seeded_pharmacy_service_id: int,
) -> None:
    body = _valid_patch_body(service_ids=[seeded_pharmacy_service_id])
    resp = await client.patch("/api/v1/sellers/me/profile", json=body)
    assert resp.status_code == 200
    profile = (await session.exec(select(SellerProfile))).first()
    rows = (
        await session.exec(
            select(SellerProfileService).where(
                SellerProfileService.seller_profile_id == profile.id
            )
        )
    ).all()
    assert {r.service_id for r in rows} == {seeded_pharmacy_service_id}


@pytest.mark.asyncio
async def test_patch_me_rejected_can_change_services(
    client: AsyncClient,
    override_as_seller_rejected: None,
    seeded_pharmacy_service_id: int,
) -> None:
    body = _valid_patch_body(service_ids=[seeded_pharmacy_service_id])
    resp = await client.patch("/api/v1/sellers/me/profile", json=body)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patch_me_approved_cannot_change_services(
    client: AsyncClient,
    override_as_seller_approved: None,
    seeded_pharmacy_service_id: int,
) -> None:
    body = _valid_patch_body(service_ids=[seeded_pharmacy_service_id])
    resp = await client.patch("/api/v1/sellers/me/profile", json=body)
    assert resp.status_code == 400
    assert "locked" in resp.json()["detail"].lower()
```

`override_as_seller_pending`/`_approved`/`_rejected` fixtures wrap an admin-toggle of `verification_status` on the seeded profile.

- [ ] **Step 2: Update the PATCH handler**

```python
@router.patch("/me/profile")
async def update_seller_profile(
    body: SellerProfileUpdateBody,
    current_user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.services.seller_services import (
        replace_profile_services,
        validate_service_ids,
    )

    assert current_user.id is not None
    profile = await _seller_profile_with_address(session, current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    if body.service_ids is not None:
        if profile.verification_status == VerificationStatus.Approved:
            raise HTTPException(
                status_code=400, detail="Services are locked after approval"
            )
        try:
            valid_ids = await validate_service_ids(session, body.service_ids)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await replace_profile_services(session, profile, valid_ids)

    if body.full_name is not None:
        first_name, last_name = split_full_name(body.full_name)
        profile.first_name = first_name
        profile.last_name = last_name
    profile.business_name = body.business_name
    profile.phone = body.phone
    profile.gst_number = body.gst_number
    profile.fssai_license = body.fssai_license
    profile.bank_account_number = body.bank_account_number
    profile.bank_ifsc = body.bank_ifsc

    address = profile.business_address
    for key, value in address_from_payload(body.address).items():
        setattr(address, key, value)

    profile.verification_status = VerificationStatus.Pending
    profile.rejection_reason = None

    await session.commit()
    await session.refresh(profile)
    return {
        "verification_status": profile.verification_status,
        "rejection_reason": profile.rejection_reason,
    }
```

- [ ] **Step 3: Run**

Run: `uv run pytest tests/test_seller_status.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/api/sellers.py backend/app/tests/test_seller_status.py
git commit -m "feat(sellers): PATCH /me/profile gates services on approval"
```

---

## Task 11: Admin applications list includes `services`

**Files:**
- Modify: `backend/app/src/app/api/sellers.py:161-201`
- Modify: `backend/app/tests/test_admin_applications.py`

- [ ] **Step 1: Write a failing test**

```python
@pytest.mark.asyncio
async def test_admin_applications_include_services(
    client: AsyncClient,
    override_as_admin: None,
    seeded_pending_seller_with_services: tuple[int, list[int]],
) -> None:
    seller_id, expected_ids = seeded_pending_seller_with_services
    resp = await client.get("/api/v1/sellers/admin/applications?status=pending")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    row = next(r for r in body if r["seller_id"] == seller_id)
    assert "business_category" not in row
    assert {s["id"] for s in row["services"]} == set(expected_ids)
```

- [ ] **Step 2: Update `_application_payload` and the list query**

Replace `_application_payload` and `admin_list_applications`:

```python
async def _application_payload(
    session: AsyncSession, profile: SellerProfile, user: User, address: Address
) -> dict:
    from app.services.seller_services import list_profile_services

    services = await list_profile_services(session, profile.id)
    return SellerApplicationPayload(
        seller_id=user.id,
        email=user.email,
        full_name=compose_full_name(profile.first_name, profile.last_name),
        business_name=profile.business_name,
        services=services,
        address=address_to_payload(address),
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


@router.get("/admin/applications")
async def admin_list_applications(
    status: str = "pending",
    _current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> List[dict]:
    if status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    stmt = (
        select(SellerProfile, User, Address)
        .join(User, User.id == SellerProfile.user_id)
        .join(Address, Address.id == SellerProfile.business_address_id)
    )
    if status != "all":
        stmt = stmt.where(SellerProfile.verification_status == VerificationStatus(status))
    stmt = stmt.order_by(desc(SellerProfile.created_at))

    result = await session.exec(stmt)
    rows = result.all()
    return [await _application_payload(session, p, u, a) for p, u, a in rows]
```

- [ ] **Step 3: Run**

Run: `uv run pytest tests/test_admin_applications.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/api/sellers.py backend/app/tests/test_admin_applications.py
git commit -m "feat(sellers): admin applications include services"
```

---

## Task 12: New endpoint — admin replace services

**Files:**
- Modify: `backend/app/src/app/api/sellers.py`
- Modify: `backend/app/tests/test_admin_applications.py`

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_admin_set_services_replaces_set(
    client: AsyncClient,
    session: AsyncSession,
    override_as_admin: None,
    seeded_pending_seller_with_services: tuple[int, list[int]],
    seeded_pharmacy_service_id: int,
) -> None:
    seller_id, _ = seeded_pending_seller_with_services
    resp = await client.patch(
        f"/api/v1/sellers/admin/{seller_id}/services",
        json={"service_ids": [seeded_pharmacy_service_id]},
    )
    assert resp.status_code == 200
    profile = (
        await session.exec(select(SellerProfile).where(SellerProfile.user_id == seller_id))
    ).first()
    rows = (
        await session.exec(
            select(SellerProfileService).where(
                SellerProfileService.seller_profile_id == profile.id
            )
        )
    ).all()
    assert {r.service_id for r in rows} == {seeded_pharmacy_service_id}


@pytest.mark.asyncio
async def test_admin_set_services_rejects_empty(
    client: AsyncClient,
    override_as_admin: None,
    seeded_pending_seller_with_services: tuple[int, list[int]],
) -> None:
    seller_id, _ = seeded_pending_seller_with_services
    resp = await client.patch(
        f"/api/v1/sellers/admin/{seller_id}/services",
        json={"service_ids": []},
    )
    assert resp.status_code == 422  # Pydantic min_length=1
```

- [ ] **Step 2: Add the endpoint**

In `backend/app/src/app/api/sellers.py`, append:

```python
from app.schemas.sellers import AdminSetServicesBody  # add at top with other schema imports


@router.patch("/admin/{seller_id}/services")
async def admin_set_services(
    seller_id: int,
    body: AdminSetServicesBody,
    _current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.services.seller_services import (
        list_profile_services,
        replace_profile_services,
        validate_service_ids,
    )

    profile_result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == seller_id)
    )
    profile = profile_result.first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    try:
        valid_ids = await validate_service_ids(session, body.service_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await replace_profile_services(session, profile, valid_ids)
    await session.commit()
    services = await list_profile_services(session, profile.id)
    return {"seller_id": seller_id, "services": [s.model_dump() for s in services]}
```

- [ ] **Step 3: Run**

Run: `uv run pytest tests/test_admin_applications.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/api/sellers.py backend/app/tests/test_admin_applications.py
git commit -m "feat(sellers): PATCH /admin/{id}/services replaces seller services"
```

---

## Task 13: `verify` approve auto-creates Store

**Files:**
- Modify: `backend/app/src/app/api/sellers.py:124-155`
- Modify: `backend/app/tests/test_admin_verify.py`

- [ ] **Step 1: Write three failing tests**

```python
@pytest.mark.asyncio
async def test_approve_creates_store(
    client: AsyncClient,
    session: AsyncSession,
    override_as_admin: None,
    seeded_pending_seller_with_services: tuple[int, list[int]],
) -> None:
    seller_id, _ = seeded_pending_seller_with_services
    resp = await client.patch(
        f"/api/v1/sellers/admin/{seller_id}/verify",
        json={"action": "approve"},
    )
    assert resp.status_code == 200
    from app.models.store import Store
    profile = (
        await session.exec(select(SellerProfile).where(SellerProfile.user_id == seller_id))
    ).first()
    stores = (
        await session.exec(select(Store).where(Store.seller_profile_id == profile.id))
    ).all()
    assert len(stores) == 1
    assert stores[0].name == profile.business_name
    assert stores[0].address_id != profile.business_address_id  # deep-copied


@pytest.mark.asyncio
async def test_approve_rejects_when_services_empty(
    client: AsyncClient,
    session: AsyncSession,
    override_as_admin: None,
    seeded_pending_seller_no_services: int,
) -> None:
    seller_id = seeded_pending_seller_no_services
    resp = await client.patch(
        f"/api/v1/sellers/admin/{seller_id}/verify",
        json={"action": "approve"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_re_approval_is_idempotent(
    client: AsyncClient,
    session: AsyncSession,
    override_as_admin: None,
    seeded_pending_seller_with_services: tuple[int, list[int]],
) -> None:
    seller_id, _ = seeded_pending_seller_with_services
    await client.patch(
        f"/api/v1/sellers/admin/{seller_id}/verify", json={"action": "approve"}
    )
    await client.patch(
        f"/api/v1/sellers/admin/{seller_id}/verify",
        json={"action": "reject", "rejection_reason": "test"},
    )
    await client.patch(
        f"/api/v1/sellers/admin/{seller_id}/verify", json={"action": "approve"}
    )
    from app.models.store import Store
    stores = (
        await session.exec(
            select(Store).join(SellerProfile, Store.seller_profile_id == SellerProfile.id)
            .where(SellerProfile.user_id == seller_id)
        )
    ).all()
    assert len(stores) == 1
```

`seeded_pending_seller_no_services` is a sibling fixture that inserts a SellerProfile but no junction rows.

- [ ] **Step 2: Update `admin_verify_seller`**

```python
@router.patch("/admin/{seller_id}/verify")
async def admin_verify_seller(
    seller_id: int,
    body: AdminVerifyBody,
    _current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.models.address import Address
    from app.models.profile import SellerProfileService
    from app.models.store import Store

    result = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == seller_id)
    )
    profile = result.first()
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    if body.action == "approve":
        # Guard: profile must have at least one service
        service_count = (
            await session.exec(
                select(func.count(SellerProfileService.id)).where(
                    SellerProfileService.seller_profile_id == profile.id
                )
            )
        ).one()
        if int(service_count) == 0:
            raise HTTPException(
                status_code=400, detail="Set services before approving"
            )

        profile.verification_status = VerificationStatus.Approved
        profile.rejection_reason = None

        # Idempotent store provisioning
        existing_store = (
            await session.exec(select(Store).where(Store.seller_profile_id == profile.id))
        ).first()
        if existing_store is None:
            biz_addr = (
                await session.exec(
                    select(Address).where(Address.id == profile.business_address_id)
                )
            ).first()
            assert biz_addr is not None
            store_addr = Address(
                address_line1=biz_addr.address_line1,
                address_line2=biz_addr.address_line2,
                landmark=biz_addr.landmark,
                city=biz_addr.city,
                state=biz_addr.state,
                pincode=biz_addr.pincode,
                country=biz_addr.country,
                latitude=biz_addr.latitude,
                longitude=biz_addr.longitude,
            )
            session.add(store_addr)
            await session.flush()
            session.add(
                Store(
                    name=profile.business_name,
                    is_active=True,
                    seller_profile_id=profile.id,
                    address_id=store_addr.id,
                )
            )
    elif body.action == "reject":
        if not body.rejection_reason or not body.rejection_reason.strip():
            raise HTTPException(status_code=400, detail="rejection_reason required when rejecting")
        profile.verification_status = VerificationStatus.Rejected
        profile.rejection_reason = body.rejection_reason
    else:
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    await session.commit()
    await session.refresh(profile)
    return {
        "seller_id": seller_id,
        "verification_status": profile.verification_status,
        "rejection_reason": profile.rejection_reason,
    }
```

- [ ] **Step 3: Run**

Run: `uv run pytest tests/test_admin_verify.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/api/sellers.py backend/app/tests/test_admin_verify.py
git commit -m "feat(sellers): approve auto-creates store, blocks empty services"
```

---

## Task 14: Stores API — expose services + enforce 1-per-seller

**Files:**
- Modify: `backend/app/src/app/api/stores.py:30-117`
- Modify: `backend/app/tests/test_stores.py`

- [ ] **Step 1: Write tests**

```python
@pytest.mark.asyncio
async def test_store_response_includes_services(
    client: AsyncClient,
    override_as_seller: None,
    seeded_seller_grocery_store: int,
) -> None:
    resp = await client.get(f"/api/v1/stores/{seeded_seller_grocery_store}")
    assert resp.status_code == 200
    body = resp.json()
    assert any(s["slug"] == "grocery" for s in body["services"])


@pytest.mark.asyncio
async def test_seller_cannot_create_second_store(
    client: AsyncClient, override_as_seller: None, seeded_seller_grocery_store: int
) -> None:
    payload = {"name": "Second Store", "address": make_address()}
    resp = await client.post("/api/v1/stores/", json=payload)
    assert resp.status_code == 409
    assert "one store" in resp.json()["detail"].lower()
```

- [ ] **Step 2: Add `services` to `StoreRead`**

In `backend/app/src/app/api/stores.py`, find the `StoreRead` Pydantic model and add `services: list[ServicePayload] = []`. Import `ServicePayload` from `app.schemas.sellers`.

- [ ] **Step 3: Populate services in every store-read site**

Wherever `StoreRead(...)` is constructed, replace with a helper:

```python
async def _build_store_read(session: AsyncSession, store: Store, seller_id: int) -> StoreRead:
    from app.services.seller_services import list_profile_services
    services = await list_profile_services(session, store.seller_profile_id)
    return StoreRead(
        id=store.id,
        name=store.name,
        address=address_to_payload(store.address),
        is_active=store.is_active,
        seller_id=seller_id,
        services=services,
        created_at=store.created_at.isoformat(),
        updated_at=store.updated_at.isoformat(),
    )
```

Use this helper in every endpoint that returns a `StoreRead`.

- [ ] **Step 4: Catch unique-constraint violations on create**

Wrap the create_store flush/commit in a try/except for `sqlalchemy.exc.IntegrityError`:

```python
from sqlalchemy.exc import IntegrityError
...
try:
    await session.commit()
except IntegrityError as exc:
    await session.rollback()
    raise HTTPException(
        status_code=409, detail="Seller may have only one store"
    ) from exc
```

- [ ] **Step 5: Run**

Run: `uv run pytest tests/test_stores.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/api/stores.py backend/app/tests/test_stores.py
git commit -m "feat(stores): expose services + enforce one store per seller"
```

---

## Task 15: Frontend types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Reuse the existing `Service` interface**

`Service` is already defined in `frontend/src/types/index.ts` from the prior catalog work (id/slug/name/description/is_active/sort_order). No new interface needed.

- [ ] **Step 2: Update `SellerProfile` and `SellerApplication`**

Replace `business_category: string;` with `services: Service[];` in both interfaces.

- [ ] **Step 3: Update `Store`**

Add `services: Service[];` to the `Store` interface.

- [ ] **Step 4: Update `mock-data.ts` if needed**

Run: `cd frontend && npx tsc --noEmit`
Fix any errors mock-data introduces (likely add `services: []` to mock store entries).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/mock-data.ts
git commit -m "feat(types): add ServiceSummary, swap business_category for services"
```

---

## Task 16: Reusable `ServicePicker` component

**Files:**
- Create: `frontend/src/components/ServicePicker.tsx`
- Create: `frontend/src/components/ServicePicker.module.css`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { Service } from "@/types";
import styles from "./ServicePicker.module.css";

interface Props {
  selectedIds: number[];
  onChange: (ids: number[]) => void;
  token?: string | null;
  disabled?: boolean;
  /** Optional pre-fetched list. If provided, the component skips the internal fetch. */
  services?: Service[];
}

export default function ServicePicker({
  selectedIds,
  onChange,
  token,
  disabled = false,
  services: providedServices,
}: Props) {
  const [services, setServices] = useState<Service[] | null>(
    providedServices ?? null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (providedServices) {
      setServices(providedServices);
      return;
    }
    let cancelled = false;
    get<Service[]>("/api/v1/catalog/services", token ?? undefined)
      .then((rows) => {
        if (!cancelled) setServices(rows);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message ?? "Failed to load services");
      });
    return () => {
      cancelled = true;
    };
  }, [token, providedServices]);

  if (error) {
    return <p className={styles.error}>{error}</p>;
  }
  if (services === null) {
    return (
      <div className={styles.grid}>
        {[1, 2, 3].map((n) => (
          <div key={n} className={styles.skeleton} />
        ))}
      </div>
    );
  }

  function toggle(id: number) {
    if (selectedIds.includes(id)) {
      onChange(selectedIds.filter((s) => s !== id));
    } else {
      onChange([...selectedIds, id]);
    }
  }

  return (
    <div className={styles.grid} role="group" aria-label="Services offered">
      {services.map((service) => {
        const checked = selectedIds.includes(service.id);
        return (
          <label
            key={service.id}
            className={`${styles.card} ${checked ? styles.cardChecked : ""}`}
          >
            <input
              type="checkbox"
              className={styles.checkbox}
              checked={checked}
              disabled={disabled}
              onChange={() => toggle(service.id)}
            />
            <span className={styles.name}>{service.name}</span>
            {service.description && (
              <span className={styles.description}>{service.description}</span>
            )}
          </label>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Create the CSS module**

```css
.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-3);
}
@media (min-width: 640px) {
  .grid {
    grid-template-columns: 1fr 1fr;
  }
}
@media (min-width: 1024px) {
  .grid {
    grid-template-columns: 1fr 1fr 1fr;
  }
}
.card {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3);
  border: 2px solid var(--color-neutral-200);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color 120ms ease, background-color 120ms ease;
}
.card:hover {
  border-color: var(--color-neutral-400);
}
.cardChecked {
  border-color: var(--color-primary-500);
  background-color: var(--color-primary-50);
}
.checkbox {
  align-self: flex-start;
  accent-color: var(--color-primary-600);
}
.name {
  font-weight: 600;
  color: var(--color-neutral-900);
}
.description {
  font-size: var(--text-sm);
  color: var(--color-neutral-600);
}
.skeleton {
  height: 80px;
  border-radius: var(--radius-md);
  background: var(--color-neutral-100);
  animation: pulse 1.2s ease-in-out infinite;
}
.error {
  color: var(--color-red-700);
  font-size: var(--text-sm);
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ServicePicker.tsx frontend/src/components/ServicePicker.module.css
git commit -m "feat(ui): add ServicePicker checkbox-grid component"
```

---

## Task 17: Wire `ServicePicker` into signup wizard step 4

**Files:**
- Modify: `frontend/src/app/seller/signup/page.tsx`

- [ ] **Step 1: Replace `businessCategory` state**

- Remove: `const [businessCategory, setBusinessCategory] = useState("");`
- Add: `const [serviceIds, setServiceIds] = useState<number[]>([]);`
- Update the resubmit pre-fill: replace `setBusinessCategory(profile.business_category)` with `setServiceIds(profile.services.map((s) => s.id))`.

- [ ] **Step 2: Replace the input in step 4**

Find the `<input>` for "Business Category" and replace its container with:

```tsx
<div className={styles.formGroup}>
  <label className={styles.label}>Services Offered</label>
  <ServicePicker
    selectedIds={serviceIds}
    onChange={setServiceIds}
  />
  {serviceIds.length === 0 && stepValidationAttempted && (
    <p className={styles.errorText}>Select at least one service</p>
  )}
</div>
```

Add a `stepValidationAttempted` boolean state that is set true on Next click (mirrors existing field validation pattern in this file).

Import: `import ServicePicker from "@/components/ServicePicker";`

- [ ] **Step 3: Update step 4 → step 5 transition**

In the existing step 4 handler that advances to step 5, add:

```ts
if (serviceIds.length === 0) {
  setStepValidationAttempted(true);
  return;
}
```

- [ ] **Step 4: Update both submit paths**

In the POST and PATCH bodies, replace `business_category: businessCategory` with `service_ids: serviceIds`.

- [ ] **Step 5: Update step 6 review**

To render service names (not just ids) in the review, the page needs the loaded `Service[]` list. Cheapest approach: fetch services once at page-level and pass into `ServicePicker` as a prop instead of letting it self-fetch.

- Edit `ServicePicker` (Task 16) to **also accept** an optional `services?: Service[]` prop. If provided, skip the internal fetch.
- In `signup/page.tsx`, add page-level state `const [services, setServices] = useState<Service[]>([]);` and fetch on mount:

```tsx
useEffect(() => {
  get<Service[]>("/api/v1/catalog/services").then(setServices).catch(() => {});
}, []);
```

- Pass `services={services}` into `<ServicePicker .../>`.
- In step 6, render:

```tsx
<dt>Services</dt>
<dd>
  {serviceIds
    .map((id) => services.find((s) => s.id === id)?.name)
    .filter(Boolean)
    .join(", ")}
</dd>
```

- [ ] **Step 6: Lint + type-check + manual smoke**

```bash
cd frontend && npx tsc --noEmit && npm run lint
npm run dev  # then open http://localhost:3000/seller/signup
```

Walk through wizard: confirm step 4 shows checkbox grid, blocks Next on zero selection, persists through to review, submits successfully against a running backend.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/seller/signup/page.tsx
git commit -m "feat(signup): replace category input with ServicePicker on step 4"
```

---

## Task 18: Admin sellers table — service badges

**Files:**
- Modify: `frontend/src/app/admin/sellers/page.tsx`

- [ ] **Step 1: Update column definition**

Find the table column whose `key` is `business_category` (around line 139). Replace:

```ts
{
  key: "services",
  label: "Services",
  render: (row) => {
    const visible = row.services.slice(0, 2);
    const extra = row.services.length - visible.length;
    return (
      <span>
        {visible.map((s) => (
          <span key={s.id} className={styles.categoryBadge}>{s.name}</span>
        ))}
        {extra > 0 && (
          <span className={styles.categoryBadge}>+{extra} more</span>
        )}
      </span>
    );
  },
},
```

- [ ] **Step 2: Update detail panel**

Around line 308, replace the line showing `reviewing.business_category` with a badge list rendered the same way as the table cell.

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean (since types updated in Task 15).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/admin/sellers/page.tsx
git commit -m "feat(admin): show service badges in sellers list and detail"
```

---

## Task 19: Admin edit-services popover

**Files:**
- Modify: `frontend/src/app/admin/sellers/page.tsx`

- [ ] **Step 1: Add edit state and handler**

In the same file:

```ts
const [editingServices, setEditingServices] = useState<{ sellerId: number; ids: number[] } | null>(null);

async function saveServices() {
  if (!editingServices || !token) return;
  await patch(
    `/api/v1/sellers/admin/${editingServices.sellerId}/services`,
    { service_ids: editingServices.ids },
    token,
  );
  // Refresh applications list using the same status filter the page already tracks.
  // The existing page state name is whatever variable currently drives the filter
  // dropdown — find it via search ("status=" in fetch URLs) and reuse here.
  // Example assuming the page uses `statusFilter`:
  const fresh = await get<SellerApplication[]>(
    `/api/v1/sellers/admin/applications?status=${statusFilter}`,
    token,
  );
  setApplications(fresh);
  // Also update `reviewing` if it's the same seller, so the detail panel reflects the change:
  setReviewing((prev) =>
    prev && prev.seller_id === editingServices.sellerId
      ? { ...prev, services: fresh.find((r) => r.seller_id === prev.seller_id)?.services ?? prev.services }
      : prev,
  );
  setEditingServices(null);
}
```

- [ ] **Step 2: Add a pencil button next to the Services row in the detail panel**

```tsx
<button
  type="button"
  className={styles.editIconBtn}
  onClick={() => setEditingServices({
    sellerId: reviewing.seller_id,
    ids: reviewing.services.map((s) => s.id),
  })}
>
  ✏️
</button>
```

- [ ] **Step 3: Render the popover**

```tsx
{editingServices && (
  <Modal
    title="Edit services"
    onClose={() => setEditingServices(null)}
    footer={
      <>
        <button className="btn btn-outline" onClick={() => setEditingServices(null)}>Cancel</button>
        <button
          className="btn btn-primary"
          disabled={editingServices.ids.length === 0}
          onClick={saveServices}
        >
          Save
        </button>
      </>
    }
  >
    <ServicePicker
      selectedIds={editingServices.ids}
      onChange={(ids) => setEditingServices({ ...editingServices, ids })}
      token={token}
    />
  </Modal>
)}
```

- [ ] **Step 4: Disable Approve when services empty**

Find the existing Approve button and add:

```ts
disabled={reviewing.services.length === 0}
title={reviewing.services.length === 0 ? "Set services before approving" : undefined}
```

- [ ] **Step 5: Lint + manual smoke**

```bash
cd frontend && npx tsc --noEmit && npm run lint
npm run dev
```

Open `/admin/sellers`, click into a pending seller, edit services, save, reload — verify persistence.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/admin/sellers/page.tsx
git commit -m "feat(admin): inline edit-services popover and approve guard"
```

---

## Task 20: Final integration sweep

**Files:** repo-wide

- [ ] **Step 1: Backend full test run**

Run from `backend/app/`: `uv run pytest -v`
Expected: all PASS.

- [ ] **Step 2: Backend lint + types**

```bash
uv run ruff check .
uv run mypy .
```

Expected: clean.

- [ ] **Step 3: Frontend build**

```bash
cd frontend && npm run build
```

Expected: success, no type errors.

- [ ] **Step 4: Manual end-to-end smoke**

Reseed DB (Task 5 step 8). Then:

1. Visit `/become-a-seller` (or `/seller/signup`) — complete the wizard with multiple services. Application should land in DB with junction rows. Verify via:
   ```bash
   uv run python -c "
   import asyncio
   from sqlalchemy.ext.asyncio import create_async_engine
   from sqlalchemy import text
   from app.core.config import settings
   async def main():
       e = create_async_engine(settings.DATABASE_URL)
       async with e.connect() as c:
           r = await c.execute(text('SELECT seller_profile_id, service_id FROM sellerprofile_service'))
           print(list(r))
       await e.dispose()
   asyncio.run(main())
   "
   ```
2. Log in as admin (`admin@khanabazaar.dev`), visit `/admin/sellers`, find the new application, edit services, then Approve. Verify a Store row was created via `/seller` dashboard for that seller.
3. Verify second-store creation fails (POST to `/api/v1/stores/` with same auth — expect 409).
4. Verify approved seller's `PATCH /sellers/me/profile` with `service_ids` returns 400.

- [ ] **Step 5: Final commit if any patch-up is needed; otherwise no-op**

- [ ] **Step 6: Push and open PR**

```bash
git push -u origin feat/seller-services
gh pr create --title "feat(sellers): services on profile + 1 store per seller" --body "$(cat <<'EOF'
## Summary
- Replace SellerProfile.business_category with many-to-many SellerProfile↔Service
- Capture services during signup wizard step 4 (checkbox grid)
- Auto-create Store on admin approval (deep-copies business address)
- Enforce 1 store per seller via UNIQUE constraint
- Admin can edit services from sellers page (pencil → checkbox popover)

## Test plan
- [x] Backend pytest suite (~165 tests including new)
- [x] Backend ruff + mypy clean
- [x] Frontend npm run build clean
- [x] Manual: signup → admin approve → store appears → 2nd store blocked

Spec: docs/superpowers/specs/2026-05-03-seller-services-design.md
EOF
)"
```

---

## Self-review notes

**Spec coverage** (cross-checked against `2026-05-03-seller-services-design.md`):

- §3 Data model → Tasks 1, 2, 4
- §4 API surface → Tasks 6, 8, 9, 10, 11, 12, 13, 14
- §5 Signup wizard → Task 17 (ServicePicker in 16)
- §6 Admin sellers review → Tasks 18, 19
- §7 Approval auto-creates Store → Task 13
- §8 Migration → Tasks 3, 4, 5
- §9 Tests → embedded in each backend task; frontend smoke in Task 17, 19, 20

**Type / endpoint consistency**:

- `ServicePayload` (backend Pydantic) ↔ `ServiceSummary` (frontend TS) — same id/slug/name shape
- Single endpoint `PATCH /sellers/admin/{seller_id}/verify` covers approve/reject (matches existing reality, not the spec's earlier `/approve` shorthand)
- `PATCH /sellers/admin/{seller_id}/services` is additive
- 422 (Pydantic) for empty `service_ids`; 400 for unknown ids; 400 for approval-with-zero-services; 400 for PATCH /me when approved; 409 for second store
- Junction model: `SellerProfileService` everywhere (no aliasing)

**Out of scope (per spec §10)**: not addressed in any task.
