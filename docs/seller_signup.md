# Seller Signup & Onboarding

Definitive guide to Khana Bazaar's seller onboarding flow — from the public landing page through email-OTP **and** phone-OTP verification, the multi-step application wizard, the pending state, admin review, and finally the approved seller dashboard with one store and multi-service inventory.

Auth is **email-OTP + phone-OTP + JWT** (PyJWT, HS256). No Firebase. Each seller has **at most one Store** (enforced by `uq_store_seller_profile`) which can offer **multiple services** (kirana, pharmacy, electronics, …).

---

## 1. Overview

| Phase | Actor | Outcome |
|-------|-------|---------|
| Landing | Anonymous visitor | Sees value props, clicks "Apply to sell" |
| Email-OTP | Anonymous visitor | Email verified, short-lived `email_token` issued |
| Phone-OTP | Anonymous visitor | Phone verified, short-lived `signup_token` issued (binds verified email + phone) |
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
| `/seller/signup` | `frontend/src/app/(operator)/seller/signup/page.tsx` | The 8-step wizard |
| `/seller/signup?resubmit=true` | same page | Pre-fills wizard from `/api/v1/sellers/me/profile`, jumps to step 5 (Personal info — phone is already verified on the existing profile), calls `PATCH /me/profile` instead of `POST /seller/register`. The resubmit path uses an authenticated session and does **not** require a new `signup_token`. |
| `/seller/signup/pending` | `frontend/src/app/seller/signup/pending/page.tsx` | Holding page that polls status every 30s |

The `/sell` page is fully static (server-rendered metadata, no API calls). The wizard is a client component wrapped in `<Suspense>` because it uses `useSearchParams`.

---

## 3. OTP signup flow (steps 1–4 of wizard)

The seller wizard now has **two** OTP gates: email (steps 1-2) and phone (steps 3-4). Both reuse the same Redis-backed primitives via a `namespace` argument (`otp:email:*` vs `otp:phone:*`). Both rate-limit at 5 sends/hour per identifier with a 60-second resend cooldown.

### 3.1 Email-OTP (steps 1-2)

```
Browser                           Backend                         Redis / Email
   |                                  |                              |
   | POST /auth/otp/request           |                              |
   | { email }                        |--- store hashed code ------> |
   |                                  |--- send email -------------> | (console in dev,
   |<------- 200 { ok: true } --------|                              |  Resend in prod)
   |                                  |                              |
   | POST /auth/seller/otp/verify     |                              |
   | { email, code }                  |--- consume_otp_key --------> |
   |                                  |                              |
   |<------- 200 { email_token } -----|  (signed 10-min JWT,         |
   |                                  |   type=seller_email)         |
```

The **seller-specific** verify route is `POST /api/v1/auth/seller/otp/verify`. It returns an `email_token`, **not** an access token. The customer route `POST /api/v1/auth/otp/verify` is the wrong one for sellers — it would create a `Customer` `User` row.

### 3.2 Phone-OTP (steps 3-4)

```
Browser                           Backend                         Redis / SMS
   |                                  |                              |
   | POST /auth/seller/phone/otp/req  |                              |
   | { email_token, phone }           |--- decode email_token        |
   |                                  |--- check duplicate phone     |
   |                                  |    in SellerProfile (DB)     |
   |                                  |--- store hashed code ------> |
   |                                  |--- send SMS --------------->  | (console in dev,
   |<------- 200 { ok: true } --------|                              |  Twilio in prod)
   |                                  |                              |
   | POST /auth/seller/phone/otp/ver  |                              |
   | { email_token, phone, code }     |--- consume_otp_key --------> |
   |                                  |                              |
   |<------- 200 { signup_token } ----|  (signed 10-min JWT,         |
   |                                  |   type=seller_signup,        |
   |                                  |   sub=email, phone=+91…)     |
```

The phone is normalized to E.164 `+91[6-9]XXXXXXXXX` server-side; non-Indian / non-mobile numbers are rejected with `400 invalid_phone`. The duplicate-phone pre-check rejects with `409 phone_already_registered` *before* dispatching the SMS — we never burn an SMS on a number that cannot ultimately register.

Error codes in `detail.error`: `rate_limited`, `invalid_code`, `too_many_attempts`, `code_expired_or_used`, `invalid_phone`, `phone_already_registered`, `email_token_expired`, `invalid_email_token`, `signup_token_expired`, `invalid_signup_token`. Wizard maps each to a toast or inline field error.

### 3.3 SMS provider switch

`SMS_PROVIDER` env var: `console` (default; logs `[SMS] to=… code=…` to stdout, used in dev/test/CI) or `twilio` (production). The Twilio path is a raw `httpx.post` to `https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json` — no SDK, mirrors the Resend integration. See `core/sms.py`.

---

## 4. The wizard — 8 steps

`frontend/src/app/(operator)/seller/signup/page.tsx` keeps everything in component state (no per-step backend roundtrip until submit). State persists only in memory — a hard refresh resets the wizard. The only persisted artefacts mid-flow are the short-lived `email_token` (after step 2) and `signup_token` (after step 4).

| Step | Subtitle | Fields | Validates | Forward action |
|------|----------|--------|-----------|----------------|
| 1 | Enter your email | `email` | required | `POST /auth/otp/request`, advance to step 2 |
| 2 | Enter the 6-digit code | `code` | 6 digits | `POST /auth/seller/otp/verify`, store `email_token`, advance |
| 3 | Verify your phone number | `phone` (10-digit local part with locked `+91` prefix) | matches `^[6-9]\d{9}$` | `POST /auth/seller/phone/otp/request`, advance to step 4 |
| 4 | Enter the 6-digit code (SMS) | `phoneCode` | 6 digits | `POST /auth/seller/phone/otp/verify`, store `signup_token`, advance |
| 5 | Tell us about yourself | `full_name` | name non-empty | local validation, advance |
| 6 | Tell us about your business | `business_name`, `service_ids[]` (via `ServicePicker`), `address` (line1/2, landmark, city, state, pincode, country, **lat/lng via map pin**) | non-empty business name; ≥1 service; line1, city, state required; pincode `^[1-9]\d{5}$`; **lat/lng required (pin must be dropped on the map)** | local validation, advance |
| 7 | Compliance & banking details | `gst_number`, `fssai_license`, `bank_account_number`, `bank_ifsc` — **all optional** | format checks if non-empty: GST regex, IFSC regex, account 9–18 digits | local validation, advance |
| 8 | Review your application | summary cards with "Edit" links per section | n/a | `POST /auth/seller/register` with `signup_token` (or `PATCH /sellers/me/profile` on resubmit) |

Validation regexes live at the top of `seller/signup/page.tsx:17-20`:

```ts
const GST_REGEX  = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
const IFSC_REGEX = /^[A-Z]{4}0[A-Z0-9]{6}$/;
const PHONE_REGEX = /^[6-9]\d{9}$/;
```

Compliance / banking fields **are stored as `NULL` when blank**; the request body sends empty strings and the backend coerces `"" → None` (see `auth.py:211-214`).

### Resubmit branch

When `?resubmit=true` is in the URL, the wizard:

1. Skips both OTP gates. The seller is already authenticated and their phone is already on the existing `SellerProfile`.
2. Pre-fills from `GET /api/v1/sellers/me/profile`.
3. Jumps to step 5 (Personal info).
4. On final submit, calls `PATCH /api/v1/sellers/me/profile` and the backend resets `verification_status → pending`, clears `rejection_reason`. The PATCH path is **authenticated** (Bearer token) and does not consume `signup_token`.

---

## 5. Backend endpoints

All paths below are prefixed with `/api/v1` (see `app/__init__.py` → `api_router` mounted at `settings.API_V1_STR`).

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/auth/otp/request` | none | Send 6-digit code to email (rate-limited) |
| POST | `/auth/seller/otp/verify` | none | Verify email code, return `email_token` (10-min, type=`seller_email`) |
| POST | `/auth/seller/phone/otp/request` | `email_token` in body | Send 6-digit SMS code; pre-checks duplicate phone |
| POST | `/auth/seller/phone/otp/verify` | `email_token` in body | Verify SMS code, return `signup_token` (10-min, type=`seller_signup`, claims `sub=email`, `phone=+91…`) |
| POST | `/auth/seller/register` | `signup_token` in body | Create `User`+`SellerProfile`+`Address`+`SellerProfileService[]`; phone read from token claims; return `access_token` |
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
  "signup_token": "<JWT, type=seller_signup, sub=email, phone=+91…>",
  "full_name": "Priya Verma",
  "business_name": "Sharma Kirana Store",
  "service_ids": [1, 3],
  "address": { "address_line1": "...", "city": "...", "state": "MH", "pincode": "411001", ... },
  "gst_number": "27AAPFU0939F1ZV",
  "fssai_license": "12345678901234",
  "bank_account_number": "012345678901",
  "bank_ifsc": "HDFC0001234"
}
```

Note: `email` and `phone` are NOT in the body — both are read from the signed `signup_token` claims, so the user cannot tamper with them between phone-OTP verification and registration. The handler also re-checks `email` and `phone` uniqueness in the DB at commit time as defence in depth (parallel signups racing).

Returns `{ access_token, token_type: "bearer", user }`. Frontend stores the token in `localStorage` under key `kb_token`.

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
3. Look up the existing `Store` by `seller_profile_id`. If none, copy the seller's `business_address` into a brand-new `Address` row (the `Store.address` is captured at first approval; later edits to the business address do **not** propagate — sellers update store address through a separate store-settings flow). The copy includes the geo fields: `latitude`, `longitude`, `digipin`, `place_id`, `location_source`. The PostGIS-generated `geo` column populates automatically.
4. The new `Store` inherits **`pin_confirmed=true`** when the seller actually pinned during signup (`location_source ∈ {pin, autocomplete}` AND lat/lng non-null). Otherwise it's `false` and the seller sees a "Confirm your store pin" banner on the dashboard until they re-pin via the store-settings flow. `delivery_radius_km` defaults to 5 km.
5. On `IntegrityError` (race between two admins approving), rollback and re-fetch — operation still reports success.

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

### `Store` (`models/store.py`)

```
name, is_active, seller_profile_id (UNIQUE), address_id,
delivery_radius_km (default 5.0, range 0.5–50.0),
pin_confirmed (default false; set true when biz_addr was pinned at signup)
```

`uq_store_seller_profile` enforces **1 seller ⇄ ≤1 store**. Created at approval, never deleted by the seller-onboarding flow. Seller dashboard exposes a slider that PATCHes `delivery_radius_km` and a banner that nags until `pin_confirmed=true`.

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
- **OTP rate-limit.** `RateLimited` on either OTP-request endpoint returns 429 with `retry_after` seconds; the wizard surfaces this as a toast. Limits are per identifier (per email; per phone) — emailing one user does not consume the SMS budget for a different victim phone.
- **`email_token` / `signup_token` expiry.** Both are 10-min signed JWTs. If `email_token` expires between steps 2 and 4 the wizard surfaces "code expired, request a new one" and the user resends the email OTP. If `signup_token` expires between step 4 and the final submit, the wizard sends the user back to step 3 (phone) to re-verify.
- **Phone tampering.** `phone` is bound to the `signup_token` signature, not in the request body — a man-in-the-middle cannot swap it at register time. The DB still has a unique index on `SellerProfile.phone`, so a successful race ends in a 409 from the server's commit-time recheck.
- **Compliance fields blank on submit.** Backend coerces `""` → `None` (`api/auth.py:211-214`); review screen will display "—" via the admin UI.
- **No seller-facing notification email** on approval/rejection — pending poll is the only mechanism today (verify in code if you wire one up).

---

## 12. Testing

Seller-flow tests in `backend/app/tests/`:

| File | Coverage |
|------|----------|
| `test_seller_register.py` | Happy path, missing/invalid address fields, invalid pincode, duplicate email, duplicate phone, invalid `signup_token`, email-token-as-signup-token rejection, empty `service_ids`, persists services, unknown service id, null/empty compliance & bank fields |
| `test_seller_phone_otp.py` | Phone OTP request happy path (asserts SMS dispatch via injected fake `SMSSender`), invalid phone format, bad email_token, duplicate phone pre-check, cooldown, verify happy path (asserts `signup_token` claims), wrong code, too many attempts, code expired |
| `test_security_signup_token.py` | `seller_email` and `seller_signup` token round-trips; cross-type rejection; expired-token rejection |
| `test_otp_phone.py` | `normalize_phone` accept/reject matrix; namespaced Redis key shape `otp:phone:*` |
| `test_sms_sender.py` | Console + Twilio sender protocol; factory selects by `SMS_PROVIDER` |
| `test_seller_status.py` | `GET /me/status` returns pending; `GET /me/profile` shape; PATCH service rules (allowed when pending/rejected, blocked when approved); customer cannot access seller endpoints |
| `test_admin_applications.py` | Default filter is `pending`; filter approved/rejected/all; invalid status → 400; non-admin → 403; counts grouping; counts zero with no profiles; revoke approved seller; payload includes services |
| `test_admin_verify.py` | Approve, reject (with reason), missing-reason → 400, non-admin → 403, approve creates Store, approve blocked when zero services, re-approval idempotent |
| `test_otp.py` | OTP request/verify/expiry/retry — shared between customer and seller flows |
| `test_auth.py` | Customer-side auth (do not confuse with seller register) |

Auth in tests is overridden via `app.dependency_overrides[get_current_user] = lambda: mock_seller` (or `mock_admin`); see `tests/conftest.py` and `tests/test_admin_verify.py:112-122` for the pattern.

Tests run against a real Postgres test database (`khanabazaar_test`) — not SQLite.
