# Seller Signup & Onboarding

Definitive guide to Khana Bazaar's seller onboarding flow — from the public landing page through OTP verification, the multi-step application wizard, the pending state, admin review, and finally the approved seller dashboard with one store and multi-service inventory.

Auth is **email-OTP + JWT** (PyJWT, HS256). No Firebase. Each seller has **at most one Store** (enforced by `uq_store_seller_profile`) which can offer **multiple services** (kirana, pharmacy, electronics, …).

---

## 1. Overview

| Phase | Actor | Outcome |
|-------|-------|---------|
| Landing | Anonymous visitor | Sees value props, clicks "Apply to sell" |
| OTP signup | Anonymous visitor | Email verified, `email_token` issued (short-lived) |
| Wizard submit | Anonymous (still no `User` row) | `User` + `SellerProfile` + `Address` + `SellerProfileService[]` created in one transaction; access-token issued; status = `pending` |
| Pending | Seller (pending) | Polls status, locked out of dashboard |
| Admin review | Admin | Approves (creates `Store`) or rejects (with reason) |
| Live | Seller (approved) | Manages store catalog and inventory |

End state: seller signs in, role = `seller`, `verification_status = approved`, can manage one `Store` and the `StoreInventory` rows under it.

---

## 2. Entry points

| Path | File | Purpose |
|------|------|---------|
| `/sell` | `frontend/src/app/sell/page.tsx` | Marketing page — value props, "How it works", FAQ, checklist, two CTAs to `/seller/signup` |
| `/seller/signup` | `frontend/src/app/seller/signup/page.tsx` | The 6-step wizard |
| `/seller/signup?resubmit=true` | same page | Pre-fills wizard from `/api/v1/sellers/me/profile`, jumps to step 3, calls `PATCH /me/profile` instead of `POST /seller/register` |
| `/seller/signup/pending` | `frontend/src/app/seller/signup/pending/page.tsx` | Holding page that polls status every 30s |

The `/sell` page is fully static (server-rendered metadata, no API calls). The wizard is a client component wrapped in `<Suspense>` because it uses `useSearchParams`.

---

## 3. OTP signup flow (steps 1–2 of wizard)

```
Browser                           Backend                         Redis / Email
   |                                  |                              |
   | POST /auth/otp/request           |                              |
   | { email }                        |--- store hashed code ------> |
   |                                  |--- send email -------------> | (console in dev,
   |<------- 200 { ok: true } --------|                              |  Resend in prod)
   |                                  |                              |
   |                                  |                              |
   | POST /auth/seller/otp/verify     |                              |
   | { email, code }                  |--- consume_otp_key --------> |
   |                                  |                              |
   |<------- 200 { email_token } -----|  (signed short-TTL JWT,      |
   |                                  |   purpose=email_verify)      |
```

Two notes that differ from the customer login flow:

- The **seller-specific** verify route is `POST /api/v1/auth/seller/otp/verify`. It returns an `email_token`, **not** an access token. Code at `backend/app/src/app/api/auth.py:155-172`.
- The customer route `POST /api/v1/auth/otp/verify` is the wrong one for sellers — it would create a `Customer` `User` and a `CustomerProfile` row. Don't reuse it for the seller path.

Error codes in the `detail.error` field: `rate_limited`, `invalid_code`, `too_many_attempts`, `code_expired_or_used`. Wizard maps each to a toast.

---

## 4. The wizard — 6 steps

`frontend/src/app/seller/signup/page.tsx` keeps everything in component state (no per-step backend roundtrip until submit). State persists only in memory — a hard refresh resets the wizard. The only persisted artefact mid-flow is the `email_token` returned by step 2; that token is itself short-lived.

| Step | Subtitle | Fields | Validates | Forward action |
|------|----------|--------|-----------|----------------|
| 1 | Enter your email | `email` | required | `POST /auth/otp/request`, advance to step 2 |
| 2 | Enter the 6-digit code | `code` | 6 digits | `POST /auth/seller/otp/verify`, store `email_token`, advance |
| 3 | Tell us about yourself | `full_name`, `phone` | name non-empty; phone matches `^[6-9]\d{9}$` | local validation, advance |
| 4 | Tell us about your business | `business_name`, `service_ids[]` (via `ServicePicker`), `address` (line1/2, landmark, city, state, pincode, country) | non-empty business name; ≥1 service; line1, city, state required; pincode `^[1-9]\d{5}$` | local validation, advance |
| 5 | Compliance & banking details | `gst_number`, `fssai_license`, `bank_account_number`, `bank_ifsc` — **all optional** | format checks if non-empty: GST regex, IFSC regex, account 9–18 digits | local validation, advance |
| 6 | Review your application | summary cards with "Edit" links per section | n/a | `POST /auth/seller/register` (or `PATCH /sellers/me/profile` on resubmit) |

Validation regexes live at the top of `seller/signup/page.tsx:17-20`:

```ts
const GST_REGEX  = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
const IFSC_REGEX = /^[A-Z]{4}0[A-Z0-9]{6}$/;
const PHONE_REGEX = /^[6-9]\d{9}$/;
```

Compliance / banking fields **are stored as `NULL` when blank**; the request body sends empty strings and the backend coerces `"" → None` (see `auth.py:211-214`).

### Resubmit branch

When `?resubmit=true` is in the URL, the wizard:

1. Skips OTP. The seller is already authenticated.
2. Pre-fills from `GET /api/v1/sellers/me/profile`.
3. Jumps to step 3.
4. On final submit, calls `PATCH /api/v1/sellers/me/profile` (multipart of all editable fields) and the backend resets `verification_status → pending`, clears `rejection_reason`.

---

## 5. Backend endpoints

All paths below are prefixed with `/api/v1` (see `app/__init__.py` → `api_router` mounted at `settings.API_V1_STR`).

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/auth/otp/request` | none | Send 6-digit code to email (rate-limited) |
| POST | `/auth/seller/otp/verify` | none | Verify code, return `email_token` (no `User` yet) |
| POST | `/auth/seller/register` | `email_token` in body | Create `User`+`SellerProfile`+`Address`+`SellerProfileService[]`; return `access_token` |
| GET  | `/sellers/me/status` | seller | `{ verification_status, rejection_reason }` |
| GET  | `/sellers/me/profile` | seller | Full `SellerProfilePayload` (incl. services + address) |
| PATCH| `/sellers/me/profile` | seller | Edit profile; locks `service_ids` once approved; resets status to `pending` |
| GET  | `/sellers/admin/applications?status=pending\|approved\|rejected\|all` | admin | List applications (default `pending`, ordered by `created_at desc`) |
| GET  | `/sellers/admin/applications/counts` | admin | `{ pending, approved, rejected, total }` |
| PATCH| `/sellers/admin/{seller_id}/verify` | admin | Body `{ action: "approve" \| "reject", rejection_reason? }`. Approve also provisions `Store`. |
| PATCH| `/sellers/admin/{seller_id}/services` | admin | Replace seller's service set |

Note the **path keying for admin endpoints uses `seller_id` = `User.id`**, not `SellerProfile.id`. Verify-handler does `where(SellerProfile.user_id == seller_id)` (`api/sellers.py:152`).

### `seller_register` request body

```json
{
  "email_token": "<JWT, purpose=email_verify>",
  "full_name": "Priya Verma",
  "phone": "9876543210",
  "business_name": "Sharma Kirana Store",
  "service_ids": [1, 3],
  "address": { "address_line1": "...", "city": "...", "state": "MH", "pincode": "411001", ... },
  "gst_number": "27AAPFU0939F1ZV",
  "fssai_license": "12345678901234",
  "bank_account_number": "012345678901",
  "bank_ifsc": "HDFC0001234"
}
```

Returns `{ access_token, token_type: "bearer", user }`. Frontend stores the token in `localStorage` under key `kb_token` (`seller/signup/page.tsx:249`).

`service_ids` must be non-empty (`SellerRegisterBody.service_ids: list[int] = Field(min_length=1)` in `schemas/sellers.py`). Validated against `Service.is_active = True` by `validate_service_ids` (`services/seller_services.py:14-34`).

---

## 6. Pending state

After successful submit (or resubmit), the wizard pushes the browser to `/seller/signup/pending`.

```
Pending page                       Backend
   |                                  |
   | (every 30 s)                     |
   | GET /sellers/me/status --------->|
   |<------- { verification_status,   |
   |          rejection_reason } -----|
   |                                  |
   if approved → router.push("/seller")
   if rejected → render rejection card with "Edit and resubmit" CTA
```

Code: `frontend/src/app/seller/signup/pending/page.tsx:33-50`. The interval is cleared on unmount and on the approval redirect.

The `/seller` layout enforces a parallel guard so a logged-in pending seller cannot reach the dashboard directly (`/seller`, `/seller/inventory`, `/seller/orders`):

```tsx
// frontend/src/app/seller/layout.tsx:50-66
get<{ verification_status: VerificationStatus; rejection_reason: string | null }>(
  "/api/v1/sellers/me/status",
  token,
)
  .then((data) => {
    setVerificationStatus(data.verification_status);
    if (data.verification_status !== "approved") {
      router.push("/seller/signup/pending");
    }
  })
```

The layout also short-circuits this guard for any path under `/seller/signup` (`isSignupRoute = pathname.startsWith("/seller/signup")`) so the wizard and pending page render without the dashboard chrome.

---

## 7. Admin review

Admin lands on `/admin/sellers` (`frontend/src/app/admin/sellers/page.tsx`).

Layout:

- Tabs across the top: `Pending | Approved | Rejected | All` with counts from `/sellers/admin/applications/counts`.
- `DataTable` of applications: business name, owner (full name + email), services badges, "submitted X ago", status pill, **Review** button.
- Review click opens a `Modal` with all the application detail (address, compliance, banking, owner, services).

Actions inside the review modal:

| Button | Visible when | Sends |
|--------|--------------|-------|
| Approve | status ∈ {pending, rejected} **and** services.length > 0 | `PATCH /sellers/admin/{seller_id}/verify` `{ action: "approve" }` |
| Reject | status ∈ {pending, approved} | shows textarea (≥10 chars), then `{ action: "reject", rejection_reason }` (button label is "Revoke" when current status is `approved`) |
| Edit services (✏️) | always | `PATCH /sellers/admin/{seller_id}/services` `{ service_ids }` |

### Approve — store provisioning

The approve handler is **idempotent and atomic**. From `api/sellers.py:158-206`:

1. Guard: at least one row must exist in `SellerProfileService` (else 400 "Set services before approving").
2. `verification_status = Approved`, `rejection_reason = None`.
3. Look up the existing `Store` by `seller_profile_id`. If none, copy the seller's `business_address` into a brand-new `Address` row (the `Store.address` is captured at first approval; later edits to the business address do **not** propagate — sellers update store address through a separate store-settings flow), then insert the `Store(name=business_name, is_active=True, ...)`.
4. On `IntegrityError` (race between two admins approving), rollback and re-fetch — operation still reports success.

### Reject

`rejection_reason` must be non-empty/whitespace; otherwise 400. `Service` selection is preserved.

### Notification email

There is **no seller-facing approval/rejection email** wired up today. `services/order_emails.py` only handles order-placement and order-status-change emails. Sellers learn about a decision via the `/seller/signup/pending` poll, not email. Add this later if needed.

---

## 8. Post-approval

When the polling `/seller/signup/pending` page sees `verification_status === "approved"`, it `router.push("/seller")`. The seller layout then:

1. Confirms `dbUser.role === "seller"`.
2. Fetches `GET /api/v1/stores/my` to populate the sidebar with the store name.
3. Renders the dashboard shell with nav: **Dashboard / Orders / Inventory** (`SELLER_NAV` in `seller/layout.tsx:10-14`).

From there the seller manages:

- The (single) `Store` row that was provisioned at approval.
- `StoreInventory` rows — keyed `(store_id, product_id)` unique — which carry `price`, `stock`, `is_available`. Sellers do **not** create master products; they pick from the admin-curated catalog and set local pricing/stock.

Service set is **frozen** after approval (`PATCH /sellers/me/profile` returns 400 "Services are locked after approval" if `service_ids` is in the body — `api/sellers.py:102-106`). Only an admin can change services post-approval, via `PATCH /sellers/admin/{seller_id}/services`.

---

## 9. Data model

### `SellerProfile` (`backend/app/src/app/models/profile.py:61-80`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | int PK | |
| `user_id` | FK `user.id` | unique (`uq_sellerprofile_user`) — one profile per user |
| `first_name` | str | from split of submitted `full_name` |
| `last_name` | str? | |
| `phone` | str(20) | unique (`ix_sellerprofile_phone`); required |
| `business_name` | str | required |
| `gst_number` | str? | nullable, format-validated frontend-side |
| `fssai_license` | str? | nullable |
| `bank_account_number` | str? | nullable |
| `bank_ifsc` | str? | nullable |
| `verification_status` | enum | `pending` (default) / `approved` / `rejected` |
| `rejection_reason` | str? | required when status = rejected |
| `business_address_id` | FK `address.id` | required |

### `VerificationStatus` enum

```python
class VerificationStatus(str, enum.Enum):
    Pending  = "pending"
    Approved = "approved"
    Rejected = "rejected"
```

### `SellerProfileService` (link table, `models/profile.py:83-95`)

Composite uniqueness `(seller_profile_id, service_id)`. No payload columns. Replaced atomically by `replace_profile_services` (`services/seller_services.py:37-59`).

### `Store` (`models/store.py:9-17`)

```
name, is_active, seller_profile_id (UNIQUE), address_id
```

`uq_store_seller_profile` enforces **1 seller ⇄ ≤1 store**. Created at approval, never deleted by the seller-onboarding flow.

### `StoreInventory` (`models/store.py:20-29`)

```
(store_id, product_id) UNIQUE, price, stock, is_available
```

Owned by the seller dashboard; not touched by the signup flow.

---

## 10. Frontend layout guard pattern

The seller layout has three `useEffect`s, each guarded by `isSignupRoute`:

```tsx
// frontend/src/app/seller/layout.tsx
const isSignupRoute = pathname.startsWith("/seller/signup");

// Effect 1 — role guard
useEffect(() => {
  if (isSignupRoute) return;
  if (!loading && (!dbUser || dbUser.role !== "seller")) {
    router.push(dbUser ? "/" : "/login");
  }
}, [loading, dbUser, router, isSignupRoute]);

// Effect 3 — verification guard
useEffect(() => {
  if (isSignupRoute || loading || !dbUser || !token) return;
  get(".../sellers/me/status", token).then((data) => {
    setVerificationStatus(data.verification_status);
    if (data.verification_status !== "approved") {
      router.push("/seller/signup/pending");
    }
  });
}, [...]);

// Render branch
if (isSignupRoute) return <>{children}</>;          // wizard / pending — no chrome
if (loading || !dbUser || dbUser.role !== "seller") return <Loading/>;
if (statusLoading || verificationStatus !== "approved") return <Loading/>;
return <DashboardLayout ...>{children}</DashboardLayout>;
```

Effect 2 fetches the store name for the sidebar — only runs on approved-seller routes.

---

## 11. Edge cases & gotchas

- **Existing customer wants to become a seller.** Today `seller_register` returns `409 email_already_registered` if a `User` exists for the email (`api/auth.py:188-189`). There is no role-transition path; the signup flow assumes a fresh email.
- **Rejected → resubmit.** `/seller/signup/pending` shows the rejection reason and a CTA that routes to `/seller/signup?resubmit=true`. The wizard PATCHes (no new `User`) and the backend stamps `verification_status = pending` again.
- **Race in admin approval.** Two admins approving simultaneously: `IntegrityError` on the unique `Store` row → rollback and re-fetch; both calls return success.
- **Approved seller editing profile.** Allowed for everything except `service_ids`. Editing also resets status to `pending` until re-approved (`api/sellers.py:128`).
- **Browser refresh mid-wizard.** State is in-memory only. Refresh on steps 3–6 returns to step 1 and the user must re-OTP. Acceptable for now.
- **OTP rate-limit.** `RateLimited` on `POST /auth/otp/request` returns 429 with `retry_after` seconds; the wizard surfaces this as a toast.
- **`email_token` expiry.** Short-TTL signed JWT (purpose=`email_verify`). On 400/410 at submit the wizard tells the user to start over.
- **Compliance fields blank on submit.** Backend coerces `""` → `None` (`api/auth.py:211-214`); review screen will display "—" via the admin UI.
- **No seller-facing notification email** on approval/rejection — pending poll is the only mechanism today (verify in code if you wire one up).

---

## 12. Testing

Seller-flow tests in `backend/app/tests/`:

| File | Coverage |
|------|----------|
| `test_seller_register.py` | Happy path, missing/invalid address fields, invalid pincode, duplicate email, invalid `email_token`, wrong-purpose token, empty `service_ids`, persists services, unknown service id, null/empty compliance & bank fields |
| `test_seller_status.py` | `GET /me/status` returns pending; `GET /me/profile` shape; PATCH service rules (allowed when pending/rejected, blocked when approved); customer cannot access seller endpoints |
| `test_admin_applications.py` | Default filter is `pending`; filter approved/rejected/all; invalid status → 400; non-admin → 403; counts grouping; counts zero with no profiles; revoke approved seller; payload includes services |
| `test_admin_verify.py` | Approve, reject (with reason), missing-reason → 400, non-admin → 403, approve creates Store, approve blocked when zero services, re-approval idempotent |
| `test_otp.py` | OTP request/verify/expiry/retry — shared between customer and seller flows |
| `test_auth.py` | Customer-side auth (do not confuse with seller register) |

Auth in tests is overridden via `app.dependency_overrides[get_current_user] = lambda: mock_seller` (or `mock_admin`); see `tests/conftest.py` and `tests/test_admin_verify.py:112-122` for the pattern.

Tests run against a real Postgres test database (`khanabazaar_test`) — not SQLite.
