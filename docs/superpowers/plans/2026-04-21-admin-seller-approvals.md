# Admin Seller Approvals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add admin-facing seller approvals module — backend list + counts endpoints, `/admin/sellers` page with filter tabs and review modal, plus dashboard surfacing (stat card, quick action, nav entry).

**Architecture:** Two new GET endpoints on `sellers.py` (list and counts) reuse `get_current_admin`. The existing `PATCH /sellers/admin/{id}/verify` endpoint is reused for approve, reject, and revoke (revoke = reject on an already-approved seller). Frontend adds one new route `/admin/sellers` plus edits to admin layout and dashboard home. No database schema change.

**Tech Stack:** FastAPI + SQLModel (backend), Next.js 16 App Router + React 19 + TypeScript (frontend), Pytest + httpx (backend tests), manual verification in dev server (frontend).

**Reference Spec:** `docs/superpowers/specs/2026-04-21-admin-seller-approvals-design.md`

---

## File Structure

### Backend
- **Modify:** `backend/app/src/app/api/sellers.py` — add `GET /admin/applications` and `GET /admin/applications/counts`
- **Create:** `backend/app/tests/test_admin_applications.py` — tests for new endpoints and revoke flow

### Frontend
- **Modify:** `frontend/src/types/index.ts` — add `SellerApplication` and `ApplicationCounts` interfaces
- **Create:** `frontend/src/app/admin/sellers/page.tsx` — applications page (tabs, table, review modal, actions)
- **Create:** `frontend/src/app/admin/sellers/page.module.css` — page styles
- **Modify:** `frontend/src/app/admin/layout.tsx` — add `Sellers` nav entry and title case
- **Modify:** `frontend/src/app/admin/page.tsx` — fetch counts, add pending stat card + quick action

---

## Task 1: Backend — List applications endpoint (tests first)

**Files:**
- Create: `backend/app/tests/test_admin_applications.py`
- Modify: `backend/app/src/app/api/sellers.py`

- [ ] **Step 1: Write the failing test file**

Create `backend/app/tests/test_admin_applications.py`:

```python
from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_user
from app.models.base import User, UserRole
from app.models.seller import SellerProfile, VerificationStatus

mock_admin = User(
    id=50, email="admin-apps@kb.com", full_name="Apps Admin",
    role=UserRole.Admin, is_active=True,
)
mock_seller_pending = User(
    id=51, email="pending@kb.com", full_name="Pending Seller",
    role=UserRole.Seller, is_active=True,
)
mock_seller_approved = User(
    id=52, email="approved@kb.com", full_name="Approved Seller",
    role=UserRole.Seller, is_active=True,
)
mock_seller_rejected = User(
    id=53, email="rejected@kb.com", full_name="Rejected Seller",
    role=UserRole.Seller, is_active=True,
)


def _profile(user_id: int, status: VerificationStatus, reason: str | None = None) -> SellerProfile:
    return SellerProfile(
        user_id=user_id,
        business_name=f"Biz {user_id}",
        business_category="grocery",
        address="1 Test Rd",
        phone="9876543210",
        gst_number="29ABCDE1234F1Z5",
        fssai_license="10020042000015",
        bank_account_number="123456789012",
        bank_ifsc="SBIN0001234",
        verification_status=status,
        rejection_reason=reason,
    )


@pytest.fixture(autouse=True)
async def seed_users_and_profiles(session: AsyncSession) -> AsyncGenerator[None, None]:
    session.add(User(**mock_admin.model_dump()))
    session.add(User(**mock_seller_pending.model_dump()))
    session.add(User(**mock_seller_approved.model_dump()))
    session.add(User(**mock_seller_rejected.model_dump()))
    await session.flush()
    session.add(_profile(mock_seller_pending.id, VerificationStatus.Pending))
    session.add(_profile(mock_seller_approved.id, VerificationStatus.Approved))
    session.add(_profile(mock_seller_rejected.id, VerificationStatus.Rejected, "Invalid GST"))
    await session.commit()
    yield


@pytest.fixture
def override_as_admin() -> Iterator[None]:
    app.dependency_overrides[get_current_admin] = lambda: mock_admin
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    yield
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_list_default_returns_pending_only(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["verification_status"] == "pending"
    assert data[0]["email"] == "pending@kb.com"
    assert data[0]["full_name"] == "Pending Seller"
    assert data[0]["seller_id"] == mock_seller_pending.id
    assert "submitted_at" in data[0]


@pytest.mark.asyncio
async def test_list_filter_approved(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications?status=approved")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["verification_status"] == "approved"


@pytest.mark.asyncio
async def test_list_filter_rejected(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications?status=rejected")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["verification_status"] == "rejected"
    assert data[0]["rejection_reason"] == "Invalid GST"


@pytest.mark.asyncio
async def test_list_all(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications?status=all")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3


@pytest.mark.asyncio
async def test_list_invalid_status_returns_400(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications?status=bogus")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_requires_admin() -> None:
    app.dependency_overrides[get_current_user] = lambda: mock_seller_pending
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/sellers/admin/applications")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `cd backend/app && uv run pytest tests/test_admin_applications.py -v`
Expected: FAIL — endpoint does not exist (404 or similar on list calls).

- [ ] **Step 3: Implement the list endpoint**

Modify `backend/app/src/app/api/sellers.py`. Add imports at the top (keep existing imports):

```python
from typing import List, Literal, Optional
from sqlalchemy.orm import selectinload
```

Append new endpoint **after** the existing `admin_verify_seller` handler (keep everything above it unchanged):

```python
ALLOWED_STATUSES = {"pending", "approved", "rejected", "all"}


def _application_payload(profile: SellerProfile, user: User) -> dict:
    return {
        "seller_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "business_name": profile.business_name,
        "business_category": profile.business_category,
        "address": profile.address,
        "phone": profile.phone,
        "gst_number": profile.gst_number,
        "fssai_license": profile.fssai_license,
        "bank_account_number": profile.bank_account_number,
        "bank_ifsc": profile.bank_ifsc,
        "verification_status": profile.verification_status,
        "rejection_reason": profile.rejection_reason,
        "submitted_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@router.get("/admin/applications")
async def admin_list_applications(
    status: str = "pending",
    _current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> List[dict]:  # type: ignore[type-arg]
    if status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    stmt = select(SellerProfile, User).join(User, User.id == SellerProfile.user_id)
    if status != "all":
        stmt = stmt.where(SellerProfile.verification_status == VerificationStatus(status))
    stmt = stmt.order_by(SellerProfile.created_at.desc())

    result = await session.exec(stmt)
    rows = result.all()
    return [_application_payload(profile, user) for profile, user in rows]
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `cd backend/app && uv run pytest tests/test_admin_applications.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/sellers.py backend/app/tests/test_admin_applications.py
git commit -m "feat(sellers): add admin list applications endpoint"
```

---

## Task 2: Backend — Counts endpoint (tests first)

**Files:**
- Modify: `backend/app/tests/test_admin_applications.py` — add counts tests
- Modify: `backend/app/src/app/api/sellers.py` — add counts endpoint

- [ ] **Step 1: Add failing counts tests**

Append to `backend/app/tests/test_admin_applications.py`:

```python
@pytest.mark.asyncio
async def test_counts_returns_grouped_totals(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications/counts")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"pending": 1, "approved": 1, "rejected": 1, "total": 3}


@pytest.mark.asyncio
async def test_counts_requires_admin() -> None:
    app.dependency_overrides[get_current_user] = lambda: mock_seller_pending
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/sellers/admin/applications/counts")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

Add a second test module for the empty case. Append:

```python
@pytest.mark.asyncio
async def test_counts_zero_when_no_profiles(
    override_as_admin: Any, session: AsyncSession
) -> None:
    # Delete all profiles to test the zero case
    from sqlmodel import delete
    await session.exec(delete(SellerProfile))  # type: ignore[call-overload]
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications/counts")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"pending": 0, "approved": 0, "rejected": 0, "total": 0}
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `cd backend/app && uv run pytest tests/test_admin_applications.py -v -k counts`
Expected: FAIL — endpoint does not exist.

- [ ] **Step 3: Implement counts endpoint**

Add to `backend/app/src/app/api/sellers.py` (append after the list endpoint). Add this import at the top alongside existing ones:

```python
from sqlalchemy import func
```

Then append the endpoint:

```python
@router.get("/admin/applications/counts")
async def admin_application_counts(
    _current_user: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    stmt = select(
        SellerProfile.verification_status,
        func.count(SellerProfile.id),
    ).group_by(SellerProfile.verification_status)
    result = await session.exec(stmt)
    rows = result.all()

    counts = {"pending": 0, "approved": 0, "rejected": 0}
    for status_value, count in rows:
        key = status_value.value if hasattr(status_value, "value") else str(status_value)
        if key in counts:
            counts[key] = count
    counts["total"] = counts["pending"] + counts["approved"] + counts["rejected"]
    return counts
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `cd backend/app && uv run pytest tests/test_admin_applications.py -v`
Expected: All 9 tests PASS.

- [ ] **Step 5: Run lint + type check**

Run: `cd backend/app && uv run ruff check . && uv run mypy .`
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/api/sellers.py backend/app/tests/test_admin_applications.py
git commit -m "feat(sellers): add admin application counts endpoint"
```

---

## Task 3: Backend — Revoke flow regression test

**Files:**
- Modify: `backend/app/tests/test_admin_applications.py` — add revoke test

The verify endpoint already supports rejecting any status. This task adds an explicit test to guarantee revoke (reject on already-approved seller) keeps working.

- [ ] **Step 1: Add the revoke test**

Append to `backend/app/tests/test_admin_applications.py`:

```python
@pytest.mark.asyncio
async def test_revoke_approved_seller(override_as_admin: Any) -> None:
    """Revoking an approved seller = calling reject with a reason."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{mock_seller_approved.id}/verify",
            json={"action": "reject", "rejection_reason": "Fraud detected post-approval"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_status"] == "rejected"
    assert data["rejection_reason"] == "Fraud detected post-approval"
```

- [ ] **Step 2: Run test, confirm it passes**

Run: `cd backend/app && uv run pytest tests/test_admin_applications.py::test_revoke_approved_seller -v`
Expected: PASS (existing endpoint already supports this path).

- [ ] **Step 3: Commit**

```bash
git add backend/app/tests/test_admin_applications.py
git commit -m "test(sellers): cover admin revoke approved seller flow"
```

---

## Task 4: Frontend — Type additions

**Files:**
- Modify: `frontend/src/types/index.ts`

`VerificationStatus` and `SellerProfile` already exist (lines 79 and 82 of the file). Only the new types are added.

- [ ] **Step 1: Add the new types**

Append to `frontend/src/types/index.ts`:

```typescript
/** A seller application as returned by GET /sellers/admin/applications. */
export interface SellerApplication {
  seller_id: number;
  email: string;
  full_name: string;
  business_name: string;
  business_category: string;
  address: string;
  phone: string;
  gst_number: string;
  fssai_license: string;
  bank_account_number: string;
  bank_ifsc: string;
  verification_status: VerificationStatus;
  rejection_reason: string | null;
  submitted_at: string;
  updated_at: string;
}

/** Per-status counts for the admin applications dashboard. */
export interface ApplicationCounts {
  pending: number;
  approved: number;
  rejected: number;
  total: number;
}
```

- [ ] **Step 2: Run lint**

Run: `cd frontend && npm run lint`
Expected: No errors in `types/index.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add SellerApplication and ApplicationCounts"
```

---

## Task 5: Frontend — Admin Sellers page scaffold (toolbar + table)

**Files:**
- Create: `frontend/src/app/admin/sellers/page.tsx`
- Create: `frontend/src/app/admin/sellers/page.module.css`

This task creates the page with filter tabs and the applications table but stubs the Review button to `console.log`. Task 6 adds the modal.

- [ ] **Step 1: Create page module CSS**

Create `frontend/src/app/admin/sellers/page.module.css`:

```css
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
  gap: 1rem;
  flex-wrap: wrap;
}

.tabs {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.tab {
  background: var(--color-surface);
  border: 1px solid var(--color-neutral-200);
  color: var(--color-neutral-600);
  padding: 0.5rem 1rem;
  border-radius: 9999px;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 500;
  transition: all 0.15s ease;
}

.tab:hover {
  background: var(--color-neutral-100);
}

.tabActive {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.tabBadge {
  margin-left: 0.4rem;
  background: rgba(255, 255, 255, 0.25);
  padding: 0.1rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.8rem;
}

.tabBadgeInactive {
  background: var(--color-neutral-200);
  color: var(--color-neutral-700);
}

.total {
  color: var(--color-neutral-500);
  font-size: 0.9rem;
}

.categoryBadge {
  display: inline-block;
  background: var(--color-neutral-100);
  color: var(--color-neutral-700);
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.8rem;
  text-transform: capitalize;
}

.statusPill {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.85rem;
  font-weight: 500;
}

.statusPending { background: #fef3c7; color: #92400e; }
.statusApproved { background: #d1fae5; color: #065f46; }
.statusRejected { background: #fee2e2; color: #991b1b; }

.ownerCell { display: flex; flex-direction: column; }
.ownerEmail { color: var(--color-neutral-500); font-size: 0.8rem; }

.reviewBtn {
  background: var(--color-primary);
  color: white;
  border: none;
  padding: 0.4rem 0.9rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
}

.reviewBtn:hover { opacity: 0.9; }

.detailsGrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-bottom: 1rem;
}

.detailsGroup { display: flex; flex-direction: column; gap: 0.5rem; }
.detailsGroupTitle {
  font-weight: 600;
  color: var(--color-neutral-800);
  margin-bottom: 0.25rem;
}
.detailsRow { display: flex; flex-direction: column; }
.detailsLabel { font-size: 0.8rem; color: var(--color-neutral-500); }
.detailsValue { color: var(--color-neutral-900); word-break: break-word; }

.rejectionCallout {
  background: #fee2e2;
  color: #991b1b;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
  font-size: 0.9rem;
}

.rejectionHint {
  font-size: 0.8rem;
  color: var(--color-neutral-500);
  margin-top: 0.35rem;
}

.dangerBtn {
  background: #dc2626;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
}

.dangerBtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.successBtn {
  background: #059669;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
}
```

- [ ] **Step 2: Create the page with tabs + table (Review button stubbed)**

Create `frontend/src/app/admin/sellers/page.tsx`:

```tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import DataTable, { Column } from "@/components/DataTable";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { SellerApplication, ApplicationCounts, VerificationStatus } from "@/types";
import styles from "./page.module.css";

type Filter = VerificationStatus | "all";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

function statusPill(status: VerificationStatus) {
  const cls =
    status === "pending" ? styles.statusPending :
    status === "approved" ? styles.statusApproved :
    styles.statusRejected;
  const icon = status === "pending" ? "🟡" : status === "approved" ? "🟢" : "🔴";
  return (
    <span className={`${styles.statusPill} ${cls}`}>
      {icon} {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

export default function AdminSellersPage() {
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();

  const [filter, setFilter] = useState<Filter>("pending");
  const [apps, setApps] = useState<SellerApplication[]>([]);
  const [counts, setCounts] = useState<ApplicationCounts>({
    pending: 0, approved: 0, rejected: 0, total: 0,
  });
  const [fetching, setFetching] = useState(true);

  const fetchAll = useCallback(async () => {
    if (!token) return;
    setFetching(true);
    try {
      const [list, c] = await Promise.all([
        get<SellerApplication[]>(
          `/api/v1/sellers/admin/applications?status=${filter}`,
          token,
        ),
        get<ApplicationCounts>(
          "/api/v1/sellers/admin/applications/counts",
          token,
        ),
      ]);
      setApps(list);
      setCounts(c);
    } catch {
      /* toast handled by calling action in later tasks */
    } finally {
      setFetching(false);
    }
  }, [filter, token]);

  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "admin")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!authLoading && dbUser && token) {
      fetchAll();
    }
  }, [authLoading, dbUser, token, router, fetchAll]);

  const columns: Column<SellerApplication>[] = [
    {
      key: "business_name",
      label: "Business",
      render: (row) => <strong>{row.business_name}</strong>,
    },
    {
      key: "owner",
      label: "Owner",
      render: (row) => (
        <div className={styles.ownerCell}>
          <span>{row.full_name}</span>
          <span className={styles.ownerEmail}>{row.email}</span>
        </div>
      ),
    },
    {
      key: "business_category",
      label: "Category",
      render: (row) => (
        <span className={styles.categoryBadge}>{row.business_category}</span>
      ),
    },
    {
      key: "submitted_at",
      label: "Submitted",
      render: (row) => timeAgo(row.submitted_at),
    },
    {
      key: "verification_status",
      label: "Status",
      render: (row) => statusPill(row.verification_status),
    },
    {
      key: "actions",
      label: "Actions",
      render: (row) => (
        <button
          className={styles.reviewBtn}
          onClick={() => console.log("TODO: open review modal for", row.seller_id)}
        >
          Review
        </button>
      ),
    },
  ];

  const emptyMsgMap: Record<Filter, string> = {
    pending: "No pending applications. 🎉",
    approved: "No approved sellers yet.",
    rejected: "No rejected applications.",
    all: "No seller applications yet.",
  };

  function tabClass(f: Filter) {
    return filter === f ? `${styles.tab} ${styles.tabActive}` : styles.tab;
  }
  function badgeClass(f: Filter) {
    return filter === f ? styles.tabBadge : `${styles.tabBadge} ${styles.tabBadgeInactive}`;
  }

  if (authLoading || fetching) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        Loading…
      </div>
    );
  }

  return (
    <>
      <div className={styles.toolbar}>
        <div className={styles.tabs}>
          <button className={tabClass("pending")} onClick={() => setFilter("pending")}>
            Pending <span className={badgeClass("pending")}>{counts.pending}</span>
          </button>
          <button className={tabClass("approved")} onClick={() => setFilter("approved")}>
            Approved <span className={badgeClass("approved")}>{counts.approved}</span>
          </button>
          <button className={tabClass("rejected")} onClick={() => setFilter("rejected")}>
            Rejected <span className={badgeClass("rejected")}>{counts.rejected}</span>
          </button>
          <button className={tabClass("all")} onClick={() => setFilter("all")}>
            All <span className={badgeClass("all")}>{counts.total}</span>
          </button>
        </div>
        <span className={styles.total}>total: {counts.total}</span>
      </div>

      <DataTable
        columns={columns}
        data={apps}
        keyField="seller_id"
        emptyMessage={emptyMsgMap[filter]}
      />
    </>
  );
}
```

- [ ] **Step 3: Run lint**

Run: `cd frontend && npm run lint`
Expected: No errors.

- [ ] **Step 4: Manually verify page loads**

Start both servers (Postgres+Redis via `docker-compose up -d`, backend `uv run uvicorn app.main:app --reload`, frontend `npm run dev`). Log in as an admin user. Visit `http://localhost:3000/admin/sellers`.
Expected: Page renders with tabs, tab counts match DB, list shows pending sellers (or empty state), Review button logs to console.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/admin/sellers/
git commit -m "feat(admin): add seller applications page scaffold"
```

---

## Task 6: Frontend — Review modal (read-only view)

**Files:**
- Modify: `frontend/src/app/admin/sellers/page.tsx`

- [ ] **Step 1: Wire the modal into the page**

In `frontend/src/app/admin/sellers/page.tsx`, replace the stub-logging Review button with modal-opening state, and add the modal render at the bottom.

Add the Modal import at the top:

```tsx
import Modal from "@/components/Modal";
```

Add state near the other `useState` hooks:

```tsx
const [reviewing, setReviewing] = useState<SellerApplication | null>(null);
```

Replace the `actions` column's `onClick` body:

```tsx
onClick={() => setReviewing(row)}
```

Before the closing `</>` fragment (just before the final `);`), add the modal:

```tsx
{reviewing && (
  <Modal
    title={`Review — ${reviewing.business_name}`}
    onClose={() => setReviewing(null)}
    footer={
      <button
        className="btn btn-outline"
        onClick={() => setReviewing(null)}
      >
        Close
      </button>
    }
  >
    {reviewing.verification_status === "rejected" && reviewing.rejection_reason && (
      <div className={styles.rejectionCallout}>
        <strong>Previous rejection:</strong> {reviewing.rejection_reason}
      </div>
    )}
    <div className={styles.detailsGrid}>
      <div className={styles.detailsGroup}>
        <div className={styles.detailsGroupTitle}>Business</div>
        <div className={styles.detailsRow}>
          <span className={styles.detailsLabel}>Name</span>
          <span className={styles.detailsValue}>{reviewing.business_name}</span>
        </div>
        <div className={styles.detailsRow}>
          <span className={styles.detailsLabel}>Category</span>
          <span className={styles.detailsValue}>{reviewing.business_category}</span>
        </div>
        <div className={styles.detailsRow}>
          <span className={styles.detailsLabel}>Address</span>
          <span className={styles.detailsValue}>{reviewing.address}</span>
        </div>
        <div className={styles.detailsRow}>
          <span className={styles.detailsLabel}>Phone</span>
          <span className={styles.detailsValue}>{reviewing.phone}</span>
        </div>
      </div>
      <div className={styles.detailsGroup}>
        <div className={styles.detailsGroupTitle}>Compliance</div>
        <div className={styles.detailsRow}>
          <span className={styles.detailsLabel}>GST Number</span>
          <span className={styles.detailsValue}>{reviewing.gst_number}</span>
        </div>
        <div className={styles.detailsRow}>
          <span className={styles.detailsLabel}>FSSAI License</span>
          <span className={styles.detailsValue}>{reviewing.fssai_license}</span>
        </div>
      </div>
      <div className={styles.detailsGroup}>
        <div className={styles.detailsGroupTitle}>Owner</div>
        <div className={styles.detailsRow}>
          <span className={styles.detailsLabel}>Full Name</span>
          <span className={styles.detailsValue}>{reviewing.full_name}</span>
        </div>
        <div className={styles.detailsRow}>
          <span className={styles.detailsLabel}>Email</span>
          <span className={styles.detailsValue}>{reviewing.email}</span>
        </div>
        <div className={styles.detailsRow}>
          <span className={styles.detailsLabel}>Submitted</span>
          <span className={styles.detailsValue}>
            {new Date(reviewing.submitted_at).toLocaleString()}
          </span>
        </div>
      </div>
      <div className={styles.detailsGroup}>
        <div className={styles.detailsGroupTitle}>Banking</div>
        <div className={styles.detailsRow}>
          <span className={styles.detailsLabel}>Account Number</span>
          <span className={styles.detailsValue}>{reviewing.bank_account_number}</span>
        </div>
        <div className={styles.detailsRow}>
          <span className={styles.detailsLabel}>IFSC</span>
          <span className={styles.detailsValue}>{reviewing.bank_ifsc}</span>
        </div>
      </div>
    </div>
  </Modal>
)}
```

- [ ] **Step 2: Run lint**

Run: `cd frontend && npm run lint`
Expected: No errors.

- [ ] **Step 3: Manually verify modal**

Reload `/admin/sellers`. Click Review on any row.
Expected: Modal opens with all fields laid out in 4 sections. For a rejected seller, the red callout shows the previous reason.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/admin/sellers/page.tsx
git commit -m "feat(admin): add review modal for seller applications"
```

---

## Task 7: Frontend — Approve action

**Files:**
- Modify: `frontend/src/app/admin/sellers/page.tsx`

- [ ] **Step 1: Wire approve**

In `frontend/src/app/admin/sellers/page.tsx`:

Add `patch` to the api import at the top:

```tsx
import { get, patch } from "@/lib/api";
```

Add a handler function inside the component, below `fetchAll`:

```tsx
async function handleApprove(sellerId: number) {
  if (!token) return;
  try {
    await patch(
      `/api/v1/sellers/admin/${sellerId}/verify`,
      { action: "approve" },
      token,
    );
    setReviewing(null);
    await fetchAll();
  } catch {
    alert("Something went wrong, please try again");
  }
}
```

Update the modal `footer` to show status-dependent buttons. Replace the previous single-button footer with:

```tsx
footer={
  <>
    <button className="btn btn-outline" onClick={() => setReviewing(null)}>
      Cancel
    </button>
    {(reviewing.verification_status === "pending" ||
      reviewing.verification_status === "rejected") && (
      <button
        className={styles.successBtn}
        onClick={() => handleApprove(reviewing.seller_id)}
      >
        Approve
      </button>
    )}
  </>
}
```

- [ ] **Step 2: Manually verify approve flow**

Reload the page, open modal for a `pending` seller, click Approve.
Expected: Modal closes, list and tab badges refresh, seller disappears from pending tab and appears in approved tab.
Also open a `rejected` seller and click Approve → seller moves to approved.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/admin/sellers/page.tsx
git commit -m "feat(admin): approve seller from review modal"
```

---

## Task 8: Frontend — Reject and Revoke actions (with reason form)

**Files:**
- Modify: `frontend/src/app/admin/sellers/page.tsx`

- [ ] **Step 1: Add reject/revoke state + handler**

Add state near the other `useState` hooks:

```tsx
const [rejectMode, setRejectMode] = useState(false);
const [rejectReason, setRejectReason] = useState("");
```

Reset these when the modal closes. Replace `setReviewing(null)` calls with a helper:

```tsx
function closeModal() {
  setReviewing(null);
  setRejectMode(false);
  setRejectReason("");
}
```

Search/replace every `setReviewing(null)` call in this file with `closeModal()`.

Add the handler:

```tsx
async function handleReject(sellerId: number) {
  if (!token || rejectReason.trim().length < 10) return;
  try {
    await patch(
      `/api/v1/sellers/admin/${sellerId}/verify`,
      { action: "reject", rejection_reason: rejectReason.trim() },
      token,
    );
    closeModal();
    await fetchAll();
  } catch {
    alert("Something went wrong, please try again");
  }
}
```

- [ ] **Step 2: Swap modal body and footer based on rejectMode**

Wrap the existing modal body (the `reviewing.verification_status === "rejected" && ...` callout + `detailsGrid`) in a conditional so it only renders when `!rejectMode`. Underneath, add the reason form for `rejectMode`:

```tsx
{rejectMode && (
  <>
    <div className={styles.detailsGroupTitle}>Rejection Reason</div>
    <textarea
      value={rejectReason}
      onChange={(e) => setRejectReason(e.target.value)}
      maxLength={500}
      rows={4}
      placeholder="Explain what the seller needs to fix…"
      style={{
        width: "100%",
        padding: "0.6rem",
        border: "1px solid var(--color-neutral-300)",
        borderRadius: "6px",
        fontFamily: "inherit",
        fontSize: "0.95rem",
        resize: "vertical",
      }}
    />
    <div className={styles.rejectionHint}>
      Common reasons: Invalid GST, Invalid FSSAI, Address mismatch, Bank details unclear.
      Minimum 10 characters.
    </div>
  </>
)}
```

Replace the modal footer with:

```tsx
footer={
  !rejectMode ? (
    <>
      <button className="btn btn-outline" onClick={closeModal}>Cancel</button>
      {(reviewing.verification_status === "pending" ||
        reviewing.verification_status === "rejected") && (
        <button
          className={styles.successBtn}
          onClick={() => handleApprove(reviewing.seller_id)}
        >
          Approve
        </button>
      )}
      {(reviewing.verification_status === "pending" ||
        reviewing.verification_status === "approved") && (
        <button
          className={styles.dangerBtn}
          onClick={() => setRejectMode(true)}
        >
          {reviewing.verification_status === "approved" ? "Revoke" : "Reject"}
        </button>
      )}
    </>
  ) : (
    <>
      <button className="btn btn-outline" onClick={() => { setRejectMode(false); setRejectReason(""); }}>
        Back
      </button>
      <button
        className={styles.dangerBtn}
        disabled={rejectReason.trim().length < 10}
        onClick={() => handleReject(reviewing.seller_id)}
      >
        Confirm Reject
      </button>
    </>
  )
}
```

- [ ] **Step 3: Run lint**

Run: `cd frontend && npm run lint`
Expected: No errors.

- [ ] **Step 4: Manually verify reject + revoke flows**

1. Reject pending seller: open modal → Reject → textarea → type 10+ chars → Confirm Reject → seller moves to rejected tab with reason visible in the modal next time.
2. Revoke approved seller: switch to approved tab → open modal → Revoke button shows → provide reason → Confirm → seller moves to rejected tab.
3. Confirm button disabled when textarea <10 chars.
4. Back button returns to detail view.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/admin/sellers/page.tsx
git commit -m "feat(admin): reject and revoke seller with reason"
```

---

## Task 9: Frontend — Admin layout nav entry

**Files:**
- Modify: `frontend/src/app/admin/layout.tsx`

- [ ] **Step 1: Update nav and title**

In `frontend/src/app/admin/layout.tsx`:

Change the `ADMIN_NAV` array (lines 8-12) to:

```tsx
const ADMIN_NAV = [
  { href: "/admin", label: "Dashboard", icon: "📊" },
  { href: "/admin/sellers", label: "Sellers", icon: "✅" },
  { href: "/admin/products", label: "Products", icon: "📦" },
  { href: "/admin/categories", label: "Categories", icon: "🏷️" },
];
```

Change the `title` ternary (lines 33-40) to include the new route:

```tsx
const title =
  pathname === "/admin"
    ? "Admin Dashboard"
    : pathname === "/admin/sellers"
      ? "Seller Applications"
      : pathname === "/admin/products"
        ? "Product Catalog"
        : pathname === "/admin/categories"
          ? "Category Management"
          : "Admin Panel";
```

- [ ] **Step 2: Manually verify**

Reload `/admin/sellers`. Sidebar shows four entries; Sellers is highlighted when on the page; title reads "Seller Applications".

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/admin/layout.tsx
git commit -m "feat(admin): add sellers nav entry to admin layout"
```

---

## Task 10: Frontend — Dashboard home stat card + quick action

**Files:**
- Modify: `frontend/src/app/admin/page.tsx`

- [ ] **Step 1: Fetch counts and render**

In `frontend/src/app/admin/page.tsx`:

Add imports at the top:

```tsx
import { MasterProduct, Category, Store, ApplicationCounts } from "@/types";
```

Add counts state next to the other `useState` calls:

```tsx
const [counts, setCounts] = useState<ApplicationCounts>({
  pending: 0, approved: 0, rejected: 0, total: 0,
});
```

Extend the `Promise.all` (lines 26-30) to also fetch counts:

```tsx
Promise.all([
  get<MasterProduct[]>("/api/v1/catalog/products", token),
  get<Category[]>("/api/v1/catalog/categories", token),
  get<Store[]>("/api/v1/stores/", token),
  get<ApplicationCounts>("/api/v1/sellers/admin/applications/counts", token),
])
  .then(([prods, cats, strs, c]) => {
    setProducts(prods);
    setCategories(cats);
    setStores(strs);
    setCounts(c);
  })
  .catch(() => {})
  .finally(() => setFetching(false));
```

Replace the `Total Sellers` StatsCard with a Pending Approvals card (inside the stats grid, around line 52):

```tsx
<StatsCard
  icon="⏳"
  label="Pending Approvals"
  value={counts.pending}
  trend={counts.pending > 0 ? "requires review" : "all caught up"}
  trendDirection={counts.pending > 0 ? "up" : "down"}
  variant={counts.pending > 0 ? "warning" : "info"}
/>
```

Add a new Quick Action card inside the `.quickActions` div (after the Manage Categories card):

```tsx
<Link href="/admin/sellers" className={styles.actionCard}>
  <div className={styles.actionIcon}>✅</div>
  <div className={styles.actionInfo}>
    <span className={styles.actionLabel}>
      Review Seller Applications{counts.pending > 0 ? ` (${counts.pending})` : ""}
    </span>
    <span className={styles.actionDescription}>
      Approve, reject, or revoke seller accounts
    </span>
  </div>
</Link>
```

- [ ] **Step 2: Run lint**

Run: `cd frontend && npm run lint`
Expected: No errors.

- [ ] **Step 3: Manually verify dashboard**

Log in as admin, go to `/admin`. Expected:
- Pending Approvals stat card shows the correct count; if >0, warning variant + "requires review".
- Quick Actions section shows "Review Seller Applications" card; label appends `(N)` when `pending > 0`.
- Clicking the card navigates to `/admin/sellers`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/admin/page.tsx
git commit -m "feat(admin): surface pending approvals on dashboard home"
```

---

## Task 11: Final verification + PR

**Files:** none

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend/app && uv run pytest -v`
Expected: All tests pass, including new `test_admin_applications.py` (10 tests).

- [ ] **Step 2: Run backend lint + type check**

Run: `cd backend/app && uv run ruff check . && uv run mypy .`
Expected: No errors.

- [ ] **Step 3: Run frontend lint**

Run: `cd frontend && npm run lint`
Expected: No errors.

- [ ] **Step 4: End-to-end manual walkthrough**

With dev servers running:
1. Log in as admin → dashboard shows pending stat card + quick action.
2. Click quick action → lands on `/admin/sellers` with pending filter active.
3. Open review modal → approve → row disappears, counts update.
4. Open review modal on new pending → reject with reason → moves to rejected tab.
5. On rejected tab → open modal → approve → re-approved.
6. On approved tab → open modal → revoke with reason → moves to rejected.
7. Log in as the affected seller in a private window → layout guard redirects correctly (pending page with reason if rejected, dashboard if approved).

- [ ] **Step 5: Open PR (only after user approval)**

Do not open the PR without explicit user permission. When user approves, run:

```bash
git push -u origin docs/admin-seller-approvals-spec
gh pr create --title "feat(admin): seller approvals module" --body "$(cat <<'EOF'
## Summary
- Add `GET /sellers/admin/applications` + `GET /sellers/admin/applications/counts` endpoints (admin only).
- Add `/admin/sellers` page with status tabs, application table, and review modal supporting approve / reject / revoke flows.
- Surface pending queue on admin dashboard home (stat card + quick action) and in the admin sidebar nav.
- Reuse existing `PATCH /sellers/admin/{id}/verify` for all approve/reject/revoke actions — revoke = reject on approved seller.

## Test plan
- [x] Backend: `uv run pytest -v` (new `test_admin_applications.py` covers list filters, counts, revoke, admin-only)
- [x] Backend: `uv run ruff check . && uv run mypy .`
- [x] Frontend: `npm run lint`
- [x] Manual: admin dashboard → `/admin/sellers` → approve / reject / revoke flows + seller guard redirect

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Commit (no changes expected)**

If any cleanup commits are needed from steps 1-4, commit them individually with descriptive messages. Otherwise nothing to commit.
