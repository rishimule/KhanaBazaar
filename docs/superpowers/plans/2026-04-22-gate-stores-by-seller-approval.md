# Gate `/stores` by Seller Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Public store-discovery endpoints (`GET /stores/`, `/stores/{id}`, `/stores/{id}/inventory`) return only stores whose owning seller has an Approved `SellerProfile`, and the three seed demo stores keep appearing after the gate ships by backfilling Approved profiles for their owners.

**Architecture:** One helper (`_get_approved_store_or_404`) on `backend/app/src/app/api/stores.py` joins `Store → SellerProfile` on `user_id == seller_id` and filters `Store.is_active AND SellerProfile.verification_status == Approved`. The helper is reused by the detail and public-inventory endpoints; the list endpoint applies the same JOIN+filter directly. Seller-auth endpoints (`/stores/my`, `/inventory/all`, writes) stay untouched. Seed `seed_database.py` grows a `SEED_PROFILES` constant that upserts an Approved `SellerProfile` per demo seller using each demo store's address block.

**Tech Stack:** FastAPI, SQLModel, asyncpg, Pydantic v2, Pytest (pytest-asyncio). No frontend or migration changes.

---

## File Structure

### Files to modify

- `backend/app/src/app/api/stores.py` — add `_get_approved_store_or_404` helper and `SellerProfile` / `VerificationStatus` imports; update `list_stores`, `get_store`, `list_store_inventory` to apply the approval filter. Leave `list_my_stores`, `create_store`, `list_store_inventory_all`, and all inventory writes untouched.
- `backend/app/tests/test_stores.py` — add a test factory `_seller_with_store(session, email, profile_status)` that creates a `User` with `role=Seller`, an optional `SellerProfile`, and an active `Store`; add seven visibility cases; fix `test_get_store_by_id_returns_nested_address` by seeding an Approved `SellerProfile` for the existing `mock_seller` fixture.
- `backend/app/scripts/seed_database.py` — add `SEED_PROFILES` constant, insert profiles between stores and inventory, wire the profiles to each matching seed store's structured address.

### Files not changed

- No migrations, no model/schema changes, no frontend changes. The visibility rule is a live query-time join on existing columns.

---

## Task 1: Add `SellerProfile` imports and the gated-store helper

**Files:**
- Modify: `backend/app/src/app/api/stores.py`

- [ ] **Step 1: Add imports**

At the top of `backend/app/src/app/api/stores.py`, alongside the existing imports, add:

```python
from app.models.seller import SellerProfile, VerificationStatus
```

- [ ] **Step 2: Add the helper below the existing `_store_read` function**

Insert immediately after `_store_read`:

```python
async def _get_approved_store_or_404(
    store_id: int, session: AsyncSession
) -> Store:
    """Return an active store whose owning seller is Approved, or 404."""
    stmt = (
        select(Store)
        .join(SellerProfile, SellerProfile.user_id == Store.seller_id)
        .where(
            Store.id == store_id,
            Store.is_active,
            SellerProfile.verification_status == VerificationStatus.Approved,
        )
    )
    result = await session.exec(stmt)
    store = result.first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store
```

- [ ] **Step 3: Run the backend test suite to confirm no regression yet**

Run: `cd backend/app && uv run pytest -q`
Expected: the existing 79 tests still pass. The helper is defined but not wired yet, so behaviour is unchanged.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/api/stores.py
git commit -m "feat(stores): add _get_approved_store_or_404 helper"
```

---

## Task 2: Gate `GET /stores/{store_id}` through the helper

**Files:**
- Modify: `backend/app/src/app/api/stores.py`
- Modify: `backend/app/tests/test_stores.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/app/tests/test_stores.py`:

```python
import pytest
from app.models.seller import SellerProfile, VerificationStatus
from sqlmodel import select
from tests._helpers import make_address


@pytest.mark.asyncio
async def test_store_detail_hidden_for_no_profile_seller(override_as_seller, client) -> None:
    body = {"name": "Ghost Store", "address": make_address()}
    create_resp = await client.post("/api/v1/stores/", json=body)
    store_id = create_resp.json()["id"]
    get_resp = await client.get(f"/api/v1/stores/{store_id}")
    assert get_resp.status_code == 404
```

If the file does not already expose `client` as a fixture to this test (confirm by scanning `tests/conftest.py`), use the exact fixture name the rest of `test_stores.py` relies on. This file currently uses `async with AsyncClient(...)` inline — follow that pattern instead:

```python
@pytest.mark.asyncio
async def test_store_detail_hidden_for_no_profile_seller(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        body = {"name": "Ghost Store", "address": make_address()}
        create_resp = await ac.post("/api/v1/stores/", json=body)
        store_id = create_resp.json()["id"]
        get_resp = await ac.get(f"/api/v1/stores/{store_id}")
    assert get_resp.status_code == 404
```

Use this second form; it matches `test_seller_can_create_store` directly above.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_stores.py::test_store_detail_hidden_for_no_profile_seller -v`
Expected: FAIL — the endpoint currently returns 200 because no approval filter is applied yet.

- [ ] **Step 3: Rewrite `get_store` to use the helper**

In `backend/app/src/app/api/stores.py`, replace the existing `get_store` body:

```python
@router.get("/{store_id}", response_model=StoreRead)
async def get_store(
    store_id: int, session: AsyncSession = Depends(get_db_session)
) -> StoreRead:
    store = await _get_approved_store_or_404(store_id, session)
    return _store_read(store)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend/app && uv run pytest tests/test_stores.py::test_store_detail_hidden_for_no_profile_seller -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/stores.py backend/app/tests/test_stores.py
git commit -m "feat(stores): gate GET /stores/{id} on approved seller profile"
```

---

## Task 3: Gate `GET /stores/{store_id}/inventory` through the helper

**Files:**
- Modify: `backend/app/src/app/api/stores.py`
- Modify: `backend/app/tests/test_stores.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/app/tests/test_stores.py`:

```python
@pytest.mark.asyncio
async def test_public_inventory_hidden_for_unapproved_store(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        body = {"name": "Hidden Inventory Store", "address": make_address()}
        create_resp = await ac.post("/api/v1/stores/", json=body)
        store_id = create_resp.json()["id"]
        inv_resp = await ac.get(f"/api/v1/stores/{store_id}/inventory")
    assert inv_resp.status_code == 404
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_stores.py::test_public_inventory_hidden_for_unapproved_store -v`
Expected: FAIL — today the endpoint returns 200 with an empty list.

- [ ] **Step 3: Rewrite `list_store_inventory` to use the helper**

Replace the existing `list_store_inventory` body in `backend/app/src/app/api/stores.py`:

```python
@router.get("/{store_id}/inventory", response_model=List[StoreInventory])
async def list_store_inventory(
    store_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> List[StoreInventory]:
    await _get_approved_store_or_404(store_id, session)
    result = await session.exec(
        select(StoreInventory).where(
            StoreInventory.store_id == store_id, StoreInventory.is_available
        )
    )
    return list(result.all())
```

The prior `is_active` check and the 404 branch inside the handler are now redundant — the helper owns both.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend/app && uv run pytest tests/test_stores.py::test_public_inventory_hidden_for_unapproved_store -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/stores.py backend/app/tests/test_stores.py
git commit -m "feat(stores): gate public inventory on approved seller profile"
```

---

## Task 4: Gate `GET /stores/` through a JOIN

**Files:**
- Modify: `backend/app/src/app/api/stores.py`
- Modify: `backend/app/tests/test_stores.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/app/tests/test_stores.py`:

```python
@pytest.mark.asyncio
async def test_stores_list_excludes_unapproved_seller_store(
    override_as_seller: Any,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        body = {"name": "Unapproved Seller Store", "address": make_address()}
        await ac.post("/api/v1/stores/", json=body)
        list_resp = await ac.get("/api/v1/stores/")
    assert list_resp.status_code == 200
    assert list_resp.json() == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_stores.py::test_stores_list_excludes_unapproved_seller_store -v`
Expected: FAIL — the list today includes the just-created store because no approval filter is applied.

- [ ] **Step 3: Rewrite `list_stores` with the JOIN**

Replace the existing `list_stores` body in `backend/app/src/app/api/stores.py`:

```python
@router.get("/", response_model=List[StoreRead])
async def list_stores(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
) -> List[StoreRead]:
    stmt = (
        select(Store)
        .join(SellerProfile, SellerProfile.user_id == Store.seller_id)
        .where(
            Store.is_active,
            SellerProfile.verification_status == VerificationStatus.Approved,
        )
        .offset(skip)
        .limit(limit)
    )
    result = await session.exec(stmt)
    return [_store_read(store) for store in result.all()]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend/app && uv run pytest tests/test_stores.py::test_stores_list_excludes_unapproved_seller_store -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/stores.py backend/app/tests/test_stores.py
git commit -m "feat(stores): gate GET /stores/ list on approved seller profile"
```

---

## Task 5: Add positive path for Approved seller + fix the pre-existing detail test

**Files:**
- Modify: `backend/app/tests/test_stores.py`

The existing `test_get_store_by_id_returns_nested_address` now fails because `mock_seller` has no `SellerProfile`. We fix it by seeding a profile, then add the Approved-path positive tests that prove the gate lets valid traffic through.

- [ ] **Step 1: Add a helper that seeds an Approved profile for the current seller**

Append to `backend/app/tests/test_stores.py`:

```python
async def _seed_approved_profile_for(user: User, session: AsyncSession) -> SellerProfile:
    """Create an Approved SellerProfile for a User. Test helper only."""
    assert user.id is not None
    profile = SellerProfile(
        user_id=user.id,
        business_name=f"{user.full_name} Mart",
        business_category="Groceries",
        phone="+919812345678",
        gst_number="27ABCDE1234F1Z5",
        fssai_license="11223344556677",
        bank_account_number="50100200300400",
        bank_ifsc="HDFC0001234",
        verification_status=VerificationStatus.Approved,
        **make_address(),
    )
    session.add(profile)
    await session.commit()
    return profile
```

- [ ] **Step 2: Update `test_get_store_by_id_returns_nested_address`**

Find `test_get_store_by_id_returns_nested_address` in `test_stores.py`. Inject the profile seeding before the `POST /stores/` call:

```python
@pytest.mark.asyncio
async def test_get_store_by_id_returns_nested_address(
    override_as_seller: Any, session: AsyncSession
) -> None:
    await _seed_approved_profile_for(mock_seller, session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        store_data = {"name": "Mini Mart", "address": make_address()}
        create_resp = await ac.post("/api/v1/stores/", json=store_data)
        store_id = create_resp.json()["id"]
        get_resp = await ac.get(f"/api/v1/stores/{store_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["address"] == store_data["address"]
```

- [ ] **Step 3: Add an explicit list-visibility positive test**

Append to `backend/app/tests/test_stores.py`:

```python
@pytest.mark.asyncio
async def test_stores_list_includes_approved_seller_store(
    override_as_seller: Any, session: AsyncSession
) -> None:
    await _seed_approved_profile_for(mock_seller, session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        body = {"name": "Approved Store", "address": make_address()}
        create_resp = await ac.post("/api/v1/stores/", json=body)
        list_resp = await ac.get("/api/v1/stores/")
    assert list_resp.status_code == 200
    rows = list_resp.json()
    names = [r["name"] for r in rows]
    assert "Approved Store" in names
    assert rows[0]["id"] == create_resp.json()["id"]
```

- [ ] **Step 4: Run the updated + new tests**

Run: `cd backend/app && uv run pytest tests/test_stores.py -v`
Expected: all existing + new tests in the file PASS, including the three visibility tests from Tasks 2/3/4 and the two added in this task.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tests/test_stores.py
git commit -m "test(stores): cover approved-seller positive path + fix stale detail test"
```

---

## Task 6: Cover Pending + Rejected visibility + `/stores/my` regression guard

**Files:**
- Modify: `backend/app/tests/test_stores.py`

- [ ] **Step 1: Add Pending and Rejected cases**

Append to `backend/app/tests/test_stores.py`:

```python
async def _set_profile_status(
    user: User, status: VerificationStatus, session: AsyncSession
) -> None:
    assert user.id is not None
    profile = (
        await session.exec(
            select(SellerProfile).where(SellerProfile.user_id == user.id)
        )
    ).first()
    assert profile is not None, "Test must seed a profile before changing its status"
    profile.verification_status = status
    session.add(profile)
    await session.commit()


@pytest.mark.asyncio
async def test_store_detail_hidden_for_pending_seller(
    override_as_seller: Any, session: AsyncSession
) -> None:
    await _seed_approved_profile_for(mock_seller, session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_resp = await ac.post(
            "/api/v1/stores/",
            json={"name": "Pending Store", "address": make_address()},
        )
        store_id = create_resp.json()["id"]
        await _set_profile_status(mock_seller, VerificationStatus.Pending, session)
        get_resp = await ac.get(f"/api/v1/stores/{store_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_store_detail_hidden_for_rejected_seller(
    override_as_seller: Any, session: AsyncSession
) -> None:
    await _seed_approved_profile_for(mock_seller, session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_resp = await ac.post(
            "/api/v1/stores/",
            json={"name": "Rejected Store", "address": make_address()},
        )
        store_id = create_resp.json()["id"]
        await _set_profile_status(mock_seller, VerificationStatus.Rejected, session)
        get_resp = await ac.get(f"/api/v1/stores/{store_id}")
    assert get_resp.status_code == 404
```

- [ ] **Step 2: Add `/stores/my` regression guard**

Append to `backend/app/tests/test_stores.py`:

```python
@pytest.mark.asyncio
async def test_my_stores_unfiltered_for_pending_seller(
    override_as_seller: Any, session: AsyncSession
) -> None:
    await _seed_approved_profile_for(mock_seller, session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(
            "/api/v1/stores/",
            json={"name": "My Draft Store", "address": make_address()},
        )
        await _set_profile_status(mock_seller, VerificationStatus.Pending, session)
        my_resp = await ac.get("/api/v1/stores/my")
    assert my_resp.status_code == 200
    names = [s["name"] for s in my_resp.json()]
    assert "My Draft Store" in names
```

- [ ] **Step 3: Run the full test file**

Run: `cd backend/app && uv run pytest tests/test_stores.py -v`
Expected: all tests PASS. Eight new or updated cases in total across Tasks 2–6 plus the pre-existing ones.

- [ ] **Step 4: Run the full suite to check for collateral damage**

Run: `cd backend/app && uv run pytest -q`
Expected: all tests PASS (previous total was 79; new count will be higher — confirm no regressions in `test_admin_applications.py`, `test_seller_status.py`, etc.). If an unrelated test breaks, it is almost certainly because it seeded a `Store` without a matching Approved `SellerProfile` and then called a public `/stores` endpoint. Fix by seeding an Approved profile for that test's seller fixture using the same helper pattern.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tests/test_stores.py
git commit -m "test(stores): cover pending/rejected visibility + my-stores regression"
```

---

## Task 7: Backfill `SellerProfile` rows for seed demo sellers

**Files:**
- Modify: `backend/app/scripts/seed_database.py`

- [ ] **Step 1: Add the import for `SellerProfile` and `VerificationStatus`**

At the top of `backend/app/scripts/seed_database.py`, alongside the existing model imports, add:

```python
from app.models.seller import SellerProfile, VerificationStatus
```

- [ ] **Step 2: Add the `SEED_PROFILES` constant**

After the `STORES` constant and before `_ADDRESS_KEYS`, insert:

```python
SEED_PROFILES = [
    {
        "seller_idx": 1,  # Ravi Sharma, seller@khanabazaar.dev
        "store_idx": 0,   # Sharma General Store
        "business_name": "Sharma General Store",
        "business_category": "Groceries",
        "phone": "+919812340001",
        "gst_number": "06AAACR5055K1Z3",
        "fssai_license": "10012022000001",
        "bank_account_number": "1234500000001",
        "bank_ifsc": "HDFC0000123",
    },
    {
        "seller_idx": 2,  # Krishna Patel, seller2@khanabazaar.dev
        "store_idx": 1,   # Krishna Supermart
        "business_name": "Krishna Supermart",
        "business_category": "Groceries",
        "phone": "+919812340002",
        "gst_number": "27AAACK8899L1Z7",
        "fssai_license": "10012022000002",
        "bank_account_number": "1234500000002",
        "bank_ifsc": "ICIC0000456",
    },
    {
        "seller_idx": 3,  # Balaji Ramaswamy, seller3@khanabazaar.dev
        "store_idx": 2,   # Balaji Fresh Market
        "business_name": "Balaji Fresh Market",
        "business_category": "Groceries",
        "phone": "+919812340003",
        "gst_number": "33AAACB7777M1Z9",
        "fssai_license": "10012022000003",
        "bank_account_number": "1234500000003",
        "bank_ifsc": "SBIN0000789",
    },
]
```

- [ ] **Step 3: Insert a new step between stores and inventory in the `seed()` function**

Locate the `"4  Inserting stores ..."` block. Immediately after it (and before `"5  Inserting inventory ..."`), insert a new block:

```python
        print("\n4b Inserting seller profiles for demo stores ...")
        for sp in SEED_PROFILES:
            seller = db_users[sp["seller_idx"]]
            assert seller.id is not None
            existing = await session.exec(
                select(SellerProfile).where(SellerProfile.user_id == seller.id)
            )
            if existing.first():
                print(f"  profile already exists: {seller.email}")
                continue
            store_addr = STORES[sp["store_idx"]]
            profile = SellerProfile(
                user_id=seller.id,
                business_name=sp["business_name"],
                business_category=sp["business_category"],
                phone=sp["phone"],
                gst_number=sp["gst_number"],
                fssai_license=sp["fssai_license"],
                bank_account_number=sp["bank_account_number"],
                bank_ifsc=sp["bank_ifsc"],
                verification_status=VerificationStatus.Approved,
                **{k: store_addr[k] for k in _ADDRESS_KEYS},
            )
            session.add(profile)
            print(f"  profile created (Approved): {seller.email}")
        await session.flush()
```

- [ ] **Step 4: Run the seed script against the dev DB**

Run: `cd backend/app && uv run python scripts/seed_database.py`
Expected: the new "4b" step prints `profile created (Approved)` for each of `seller@khanabazaar.dev`, `seller2@khanabazaar.dev`, `seller3@khanabazaar.dev`. Re-running is idempotent (prints `profile already exists`).

- [ ] **Step 5: Verify DB state**

Run:
```bash
docker exec -i $(docker ps --filter "ancestor=postgres:15" -q | head -1) \
  psql -U postgres -d khanabazaar -c "
SELECT u.email, sp.verification_status
FROM \"user\" u
LEFT JOIN sellerprofile sp ON sp.user_id = u.id
WHERE u.email IN ('seller@khanabazaar.dev', 'seller2@khanabazaar.dev', 'seller3@khanabazaar.dev')
ORDER BY u.email;
"
```
Expected: three rows, each with `verification_status = Approved`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/scripts/seed_database.py
git commit -m "feat(seed): backfill Approved profiles for demo store sellers"
```

---

## Task 8: Backend quality gates

**Files:** (no changes expected — verification step)

- [ ] **Step 1: Run ruff**

Run: `cd backend/app && uv run ruff check .`
Expected: PASS.

- [ ] **Step 2: Run mypy**

Run: `cd backend/app && uv run mypy .`
Expected: PASS.

- [ ] **Step 3: Run the full test suite**

Run: `cd backend/app && uv run pytest -v`
Expected: all tests PASS (previous 79 plus 6 new cases from Tasks 2–6 ≈ 85+). If a type or lint error appears in `stores.py` or the test file, fix it in place. Do NOT add `# type: ignore` unless the same pattern was already present elsewhere.

- [ ] **Step 4: Commit any fixes**

If changes were needed:
```bash
git add -A
git commit -m "chore(stores): fix lint/type errors after gating"
```

Skip if the gates passed clean.

---

## Task 9: End-to-end manual verification

**Files:** (no changes expected)

- [ ] **Step 1: Ensure migrations + seeds are current**

Run:
```bash
cd backend/app
uv run alembic upgrade head
uv run python scripts/seed_database.py
uv run python scripts/seed_seller_applications.py
```

- [ ] **Step 2: Confirm backend + frontend are running**

Backend: `cd backend/app && uv run uvicorn app.main:app --reload` (already running on port 8000 in this environment — skip if alive).
Frontend: `cd frontend && npm run dev` (port 3000).

- [ ] **Step 3: Verify `/stores` shows the three demo stores**

Navigate to `http://localhost:3000/stores` (log in as a customer first if the page gates on auth).
Expected: three store cards — Sharma General Store, Krishna Supermart, Balaji Fresh Market.

- [ ] **Step 4: Verify direct-link 404 for unapproved store**

Create a throwaway seller via `/seller/signup` (do not approve). Log in as an admin, visit `/admin/sellers`, confirm the new seller is Pending. From the DB, find the new seller's (likely zero) stores; if zero, test the revocation path instead by revoking one of the approved seed sellers:

- Log in as `admin@khanabazaar.dev`, open `/admin/sellers`, open Ravi Sharma's application, click Reject with reason "manual verification test".
- Reload `http://localhost:3000/stores` → Sharma General Store is gone.
- Navigate directly to `http://localhost:3000/stores/<sharma-id>` → "Store Not Found" card.
- Re-approve Ravi Sharma → Sharma General Store reappears on `/stores`.

- [ ] **Step 5: Verify `/seller` dashboard is unfiltered**

Log in as `seller@khanabazaar.dev` (Ravi Sharma). While Ravi is **Rejected** (from the step above), visit `/seller` and `/seller/inventory`. Expected: Sharma General Store still appears in the seller's own dashboard because `/stores/my` and `/stores/{id}/inventory/all` are not gated by approval.

- [ ] **Step 6: No commit — this is a verification step**

If any check fails, fix the underlying task, do not patch around it at this level.

---

## Self-Review

- **Spec coverage:**
  - Gate `/stores/` list — Task 4.
  - Gate `/stores/{id}` detail — Task 2.
  - Gate `/stores/{id}/inventory` public — Task 3.
  - `_get_approved_store_or_404` helper — Task 1.
  - `/stores/my` stays unfiltered — Task 6 regression guard.
  - Seed backfill for Ravi / Krishna / Balaji — Task 7.
  - Tests 1–7 from the spec's Testing section — covered in Tasks 2 (no-profile detail), 3 (public inventory 404), 4 (list exclusion), 5 (approved positive path + detail fix), 6 (Pending/Rejected detail + `/my` unfiltered).
  - Deploy-order safety (spec's "Rollout" section) — tasks are ordered so the seed change lands in the same PR as the gate, and Task 9 exercises the seeded dev DB end-to-end.

- **Placeholder scan:** No TBDs, TODOs, or "similar to Task N". All code blocks are complete.

- **Type / signature consistency:**
  - `_get_approved_store_or_404(store_id: int, session: AsyncSession) -> Store` — same signature in Tasks 1, 2, 3.
  - `_seed_approved_profile_for(user: User, session: AsyncSession) -> SellerProfile` — same signature in Tasks 5, 6.
  - `_set_profile_status(user, status, session)` — introduced in Task 6 only, used only there.
  - `SEED_PROFILES[*]["seller_idx"]` indexes into `db_users` which is populated by the existing users loop before step 4b runs; `STORES[store_idx]` indexes into the already-defined `STORES` constant. Both indices verified against `TEST_USERS` (admin=0, seller=1, seller2=2, seller3=3) and the three `STORES` entries in the existing file.
