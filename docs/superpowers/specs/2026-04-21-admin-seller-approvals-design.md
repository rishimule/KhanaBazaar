# Admin Seller Approvals — Design

Status: Draft
Date: 2026-04-21
Scope: Admin dashboard feature for reviewing, approving, rejecting, and revoking seller applications.

---

## 1. Purpose

Sellers register via the 6-step wizard documented in [docs/seller_signup.md](../../seller_signup.md), which lands every new application in `verification_status = "pending"`. Today the backend endpoint `PATCH /sellers/admin/{seller_id}/verify` exists, but there is no list endpoint and no admin UI. Admins have no way to enumerate or review applications.

This feature closes the loop:

- Admin sees all seller applications in one place, filtered by status.
- Admin reviews a full application (business, compliance, banking, owner info) and approves or rejects with a reason.
- Admin can revoke an already-approved seller (same flow as reject) if fraud or policy violations are discovered later.

Existing seller-side behavior is not changed. The pending page polling loop already reflects admin decisions within 30 seconds.

---

## 2. Scope & Non-Goals

In scope:

- New backend endpoints to list seller applications and return per-status counts.
- New admin route `/admin/sellers` with filter tabs, table, review modal.
- Dashboard surfacing: pending count stat card + quick-action card + sidebar nav entry.
- Revoke = reject on already-approved seller (reuses existing verify endpoint).

Out of scope:

- Audit log of approval/revoke history.
- Email notifications to sellers on decision (seller polls, per existing design).
- Bulk approve/reject.
- Pagination (MVP seller volume is low).
- Admin-side search by business name.
- Admin bootstrap / admin management.

---

## 3. Architecture Overview

Two new backend endpoints, no schema change, one new admin page plus small edits to the admin dashboard home and layout.

```
Admin (browser)
  │
  ├─ GET /admin                              → stats + quick actions (+ pending badge)
  │
  └─ GET /admin/sellers                      → applications page
        │
        ├─ GET  /api/v1/sellers/admin/applications?status=…   (NEW)
        ├─ GET  /api/v1/sellers/admin/applications/counts     (NEW)
        └─ PATCH /api/v1/sellers/admin/{seller_id}/verify     (existing, reused)
```

All new endpoints live in `backend/app/src/app/api/sellers.py` next to the existing `admin_verify_seller` handler and reuse `get_current_admin`.

No database schema change. The `SellerProfile` table already has every field the UI needs; owner info (`email`, `full_name`) is fetched by joining `User`.

---

## 4. Backend Design

### 4.1 List endpoint

```
GET /api/v1/sellers/admin/applications?status={pending|approved|rejected|all}
Auth: Bearer JWT (admin)
```

- `status` query parameter. Default: `pending`. Accepts `pending`, `approved`, `rejected`, `all`.
- Unknown value → 400 with `{"detail": "invalid status"}`.
- Ordering: `SellerProfile.created_at DESC` (newest first).
- Query shape: `select(SellerProfile, User).join(User, User.id == SellerProfile.user_id)`.

Response 200:

```json
[
  {
    "seller_id": 42,
    "email": "priya@example.com",
    "full_name": "Priya Verma",
    "business_name": "Sharma Kirana Store",
    "business_category": "grocery",
    "address": "12 MG Road, Bangalore 560001",
    "phone": "9876543210",
    "gst_number": "29AAPFU0939F1ZV",
    "fssai_license": "10012345000123",
    "bank_account_number": "123456789012",
    "bank_ifsc": "HDFC0001234",
    "verification_status": "pending",
    "rejection_reason": null,
    "submitted_at": "2026-04-15T10:30:00Z",
    "updated_at": "2026-04-15T10:30:00Z"
  }
]
```

`seller_id` is the `user.id` (same convention as existing verify endpoint). `submitted_at` is `SellerProfile.created_at`.

### 4.2 Counts endpoint

```
GET /api/v1/sellers/admin/applications/counts
Auth: Bearer JWT (admin)
```

Response 200:

```json
{ "pending": 4, "approved": 12, "rejected": 2, "total": 18 }
```

Implementation: a single `GROUP BY verification_status` query. Absent buckets default to 0.

### 4.3 Verify endpoint (existing, reused)

`PATCH /api/v1/sellers/admin/{seller_id}/verify` already accepts:

```json
{ "action": "approve" }
{ "action": "reject", "rejection_reason": "..." }
```

No changes required. Revoke = call `reject` on a seller whose current status is `approved`. The seller's next poll of `/sellers/me/status` (30s interval) returns `rejected`, and the seller layout guard redirects them to the pending page with the reason.

### 4.4 Backend tests

New file: `backend/app/tests/test_admin_applications.py`.

- List with each `status` value returns only matching rows.
- List with `status=all` returns every row.
- List with invalid `status` returns 400.
- List orders by `created_at DESC`.
- List as non-admin (seller or customer) returns 403.
- Counts returns correct grouped totals.
- Counts returns zeros when no sellers exist.
- Revoke flow: create approved seller, call verify with `reject`+reason, assert status flipped to `rejected` and reason stored.
- Reject without reason returns 400 (already covered by existing test — verify it stays green).

---

## 5. Frontend Design — `/admin/sellers`

### 5.1 Route & file

New file: `frontend/src/app/admin/sellers/page.tsx` (+ `page.module.css`).

Route is protected by existing `/admin/layout.tsx` which already redirects non-admins.

### 5.2 Page layout

```
┌─ Toolbar ─────────────────────────────────────────────┐
│  [Pending (4)]  [Approved (12)]  [Rejected (2)]  [All]│
│                                         total: 18     │
└───────────────────────────────────────────────────────┘
┌─ DataTable ───────────────────────────────────────────┐
│ Business       │ Owner      │ Category │ Submitted │ Status │ Actions │
│ Sharma Kirana  │ Priya V.   │ Grocery  │ 2d ago    │ 🟡 Pending │ [Review] │
│ ...                                                                    │
└───────────────────────────────────────────────────────┘
```

### 5.3 Filter tabs

- Tab buttons labeled with count badges fetched from the counts endpoint.
- Default active tab: `pending`.
- Clicking a tab refetches the list with `?status=<tab>`.
- Counts are refetched after every approve/reject/revoke so badges stay live.

### 5.4 Table columns

| Column | Render |
|--------|--------|
| Business Name | `<strong>{business_name}</strong>` |
| Owner | `full_name` with small gray `email` below |
| Category | Badge (reuse `styles.categoryBadge` pattern from products page) |
| Submitted | Relative time (`2d ago`) computed from `submitted_at` |
| Status | Colored pill: 🟡 pending, 🟢 approved, 🔴 rejected |
| Actions | `Review` button opens modal |

### 5.5 Review modal

Reuses `components/Modal`. Body shows all application fields in a two-column labeled grid:

```
Business                         Compliance
  Business name                    GST number
  Category                         FSSAI license
  Address
  Phone                          Banking
                                   Account number
Owner                              IFSC code
  Full name
  Email
  Submitted date
```

If `verification_status === "rejected"`, a red callout at the top shows the previous `rejection_reason`.

Footer buttons depend on current status:

| Status     | Buttons                              |
|------------|--------------------------------------|
| pending    | `[Cancel] [Reject] [Approve]`        |
| approved   | `[Cancel] [Revoke]`                  |
| rejected   | `[Cancel] [Approve]`                 |

### 5.6 Approve action

Click `Approve` → `PATCH /sellers/admin/{seller_id}/verify` with `{"action":"approve"}` → close modal → refetch list + counts.

### 5.7 Reject / Revoke action

Click `Reject` (or `Revoke`) → modal body swaps to a rejection-reason form:

- Textarea, required, min 10 chars, max 500 chars.
- Helper text beneath: `"Common reasons: Invalid GST, Invalid FSSAI, Address mismatch, Bank details unclear"`.
- Buttons: `[Back] [Confirm Reject]`. Confirm is disabled until textarea ≥10 chars.

Confirm → `PATCH /sellers/admin/{seller_id}/verify` with `{"action":"reject","rejection_reason":<text>}` → close modal → refetch.

### 5.8 Loading & empty states

- In-flight list fetch: existing DataTable loading convention.
- Empty pending: `"No pending applications. 🎉"`
- Empty approved: `"No approved sellers yet."`
- Empty rejected: `"No rejected applications."`

---

## 6. Frontend Design — Dashboard Home & Nav

### 6.1 `admin/layout.tsx`

Add nav entry:

```ts
const ADMIN_NAV = [
  { href: "/admin",           label: "Dashboard",  icon: "📊" },
  { href: "/admin/sellers",   label: "Sellers",    icon: "✅" }, // NEW
  { href: "/admin/products",  label: "Products",   icon: "📦" },
  { href: "/admin/categories",label: "Categories", icon: "🏷️" },
];
```

Extend `title` ternary to include `pathname === "/admin/sellers"` → `"Seller Applications"`.

### 6.2 `admin/page.tsx`

Extend the existing `Promise.all` to also fetch counts:

```ts
Promise.all([
  get<MasterProduct[]>("/api/v1/catalog/products", token),
  get<Category[]>("/api/v1/catalog/categories", token),
  get<Store[]>("/api/v1/stores/", token),
  get<ApplicationCounts>("/api/v1/sellers/admin/applications/counts", token),
])
```

Add `StatsCard` to the stats grid:

```tsx
<StatsCard
  icon="⏳"
  label="Pending Approvals"
  value={counts.pending}
  trend={counts.pending > 0 ? "requires review" : "all caught up"}
  trendDirection={counts.pending > 0 ? "up" : "neutral"}
  variant={counts.pending > 0 ? "warning" : "info"}
/>
```

Add a Quick Action card linking to `/admin/sellers`:

```tsx
<Link href="/admin/sellers" className={styles.actionCard}>
  <div className={styles.actionIcon}>✅</div>
  <div className={styles.actionInfo}>
    <span className={styles.actionLabel}>
      Review Seller Applications
      {counts.pending > 0 ? ` (${counts.pending})` : ""}
    </span>
    <span className={styles.actionDescription}>
      Approve, reject, or revoke seller accounts
    </span>
  </div>
</Link>
```

### 6.3 Types

`frontend/src/types/index.ts` additions (reuse `VerificationStatus` if already defined for seller signup — do not duplicate):

```ts
export type VerificationStatus = "pending" | "approved" | "rejected";

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

export interface ApplicationCounts {
  pending: number;
  approved: number;
  rejected: number;
  total: number;
}
```

### 6.4 API helper

`frontend/src/lib/api.ts` already exposes `get` and `patch`. No new helpers needed.

---

## 7. Error Handling & Edge Cases

| Scenario | Backend | UI behavior |
|----------|---------|-------------|
| Non-admin hits list/counts | 403 | Layout redirect makes this unreachable in UI |
| List: invalid status | 400 | UI only sends valid values |
| Verify: invalid action | 400 | UI hardcodes action |
| Verify: reject without reason | 400 | Confirm disabled until textarea ≥10 chars |
| Seller deleted mid-review | 404 on verify | Toast `"Seller not found"` + refetch |
| Network / 5xx | — | Toast `"Something went wrong, please try again"` |
| Two admins approve concurrently | second call 200 (idempotent state set) | Acceptable; refetch reflects truth |

Stale modal: another admin changes status while the first admin has the modal open. The first admin's action still succeeds (idempotent set). Refetch after close reconciles state.

Resubmit race: a seller may resubmit their profile via `PATCH /sellers/me/profile` while the admin is reviewing — that endpoint resets `verification_status` to `pending` and clears the reason. Admin's pending decision still applies. Acceptable at MVP.

---

## 8. Testing

### Backend

New file `backend/app/tests/test_admin_applications.py` covering the cases listed in §4.4. Follow the existing pattern in `test_admin_verify.py` (dependency overrides via `app.dependency_overrides`, test DB `khanabazaar_test`).

### Frontend

No unit test framework is configured in the frontend. Verification is manual against the dev server (`npm run dev` + backend running):

- Log in as admin → dashboard shows pending stat card.
- Click "Review Seller Applications" → lands on `/admin/sellers`, pending tab active, counts match.
- Open review modal → every field renders.
- Approve pending seller → row leaves pending tab, counts update.
- Reject pending seller → reason required, row moves to rejected tab with reason visible on expand.
- Switch to approved tab → Revoke → seller moves to rejected, reason stored.
- Switch to rejected tab → Approve → seller re-approved.
- Log in as the affected seller in a private window → layout guard redirects correctly on status flip.

---

## 9. File Map

| File | Change |
|------|--------|
| `backend/app/src/app/api/sellers.py` | Add `GET /admin/applications`, `GET /admin/applications/counts` |
| `backend/app/tests/test_admin_applications.py` | New test file |
| `frontend/src/app/admin/sellers/page.tsx` | New page: tabs, table, review modal |
| `frontend/src/app/admin/sellers/page.module.css` | New styles |
| `frontend/src/app/admin/layout.tsx` | Add `Sellers` nav entry + title case |
| `frontend/src/app/admin/page.tsx` | Fetch counts, add stat card + quick action |
| `frontend/src/types/index.ts` | Add `SellerApplication`, `ApplicationCounts` (reuse `VerificationStatus` if defined) |

---

## 10. Open Questions

None at spec time. All decisions locked during brainstorming:

- Scope: all sellers with status filter, default pending (Q1)
- Revoke: reuse reject on approved (Q2)
- UI: table + modal (Q3)
- Endpoints: list + separate counts endpoint, no pagination (Q4)
- Dashboard: both stat card and quick action (Q5)
- Rejection reason: free-text with helper hint (Q6)
