# Seller Signup & Onboarding

End-to-end guide for how new sellers register on KhanaBazaar, how admin approval works, and how the verification guard protects the seller dashboard.

---

## Overview

Seller onboarding is a separate flow from customer login. It consists of:

1. **Email verification** — prove ownership of the email address (OTP)
2. **Profile submission** — business, compliance, and banking details (6-step wizard)
3. **Pending approval** — account is created but locked until an admin approves
4. **Dashboard access** — once approved, seller can create stores and manage inventory

Sellers are never auto-approved. Every new seller application lands in `pending` state and requires an admin action.

---

## Database Schema

### `SellerProfile` table

Created by migration `d6342a56eaf6_add_sellerprofile_table.py`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer | PK, auto |
| `user_id` | integer | FK → `user.id`, unique (one-to-one) |
| `business_name` | text | |
| `business_category` | text | `grocery \| pharmacy \| electronics \| general` |
| `address` | text | |
| `phone` | text | 10-digit Indian mobile |
| `gst_number` | text | 15-char GST format |
| `fssai_license` | text | Food safety license number |
| `bank_account_number` | text | |
| `bank_ifsc` | text | 11-char IFSC format |
| `verification_status` | enum | `pending \| approved \| rejected` |
| `rejection_reason` | text, nullable | Set by admin on rejection |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

The corresponding `user` row has `role = "seller"`. Both rows are created atomically in a single transaction during registration.

---

## Auth Flow (New Registrations)

Seller signup uses a **two-token pattern** to separate email verification from account creation.

```
Client                          Backend
  |                                |
  |-- POST /auth/otp/request ----->|  (existing endpoint, shared with customer login)
  |<-- { ok: true } --------------|
  |                                |
  |-- POST /auth/seller/otp/verify |  (seller-specific — does NOT create a user)
  |   { email, code }             |
  |<-- { email_token } ------------|  short-lived JWT (10 min), type="seller_otp"
  |                                |
  |-- POST /auth/seller/register ->|  (creates User + SellerProfile atomically)
  |   { email_token, full_name,   |
  |     phone, business_name, ... }|
  |<-- { access_token, user } -----|  regular JWT for future requests
```

### Why a separate OTP verify endpoint?

`POST /auth/otp/verify` (the customer endpoint) creates a `User` row on first use. If we reused it for sellers, the user would be created as a `Customer` before the business details are collected. The seller-specific endpoint only validates the OTP and returns a proof-of-email token — no user is created until the full registration payload is submitted.

### Email token

```python
payload = {
    "sub": email,          # verified email address
    "type": "seller_otp",  # guards against token reuse in wrong endpoint
    "iat": now,
    "exp": now + timedelta(minutes=10),
}
```

The token is signed with `JWT_SECRET`. It is single-use in practice because OTP codes are consumed on verify (`consume_otp_key`), so re-requesting a new token requires going through OTP again.

---

## API Reference

All routes are prefixed with `/api/v1`.

### OTP request (shared)

```
POST /auth/otp/request
Body: { "email": "seller@example.com" }
Response 200: { "ok": true, "expires_in": 600 }
Response 429: { "detail": { "error": "rate_limited", "retry_after": <seconds> } }
```

### Seller OTP verify

```
POST /auth/seller/otp/verify
Body: { "email": "seller@example.com", "code": "123456" }
Response 200: { "email_token": "<jwt>" }
Response 400: { "detail": { "error": "invalid_code" } }
Response 410: { "detail": { "error": "code_expired_or_used" } }
Response 429: { "detail": { "error": "too_many_attempts" } }
```

### Seller register

```
POST /auth/seller/register
Body: {
  "email_token": "<jwt from seller OTP verify>",
  "full_name": "Priya Verma",
  "phone": "9876543210",
  "business_name": "Sharma Kirana Store",
  "business_category": "grocery",
  "address": "12 MG Road, Bangalore 560001",
  "gst_number": "29AAPFU0939F1ZV",
  "fssai_license": "10012345000123",
  "bank_account_number": "123456789012",
  "bank_ifsc": "HDFC0001234"
}
Response 200: { "access_token": "<jwt>", "token_type": "bearer", "user": { ... } }
Response 409: { "detail": { "error": "email_already_registered" } }
Response 400: { "detail": { "error": "invalid_email_token" } }
Response 410: { "detail": { "error": "email_token_expired" } }
```

### Seller status (poll)

```
GET /sellers/me/status
Auth: Bearer JWT (seller)
Response 200: {
  "verification_status": "pending" | "approved" | "rejected",
  "rejection_reason": "<string>" | null
}
```

### Seller profile (resubmit flow)

```
GET /sellers/me/profile
Auth: Bearer JWT (seller)
Response 200: { ...all SellerProfile fields... }

PATCH /sellers/me/profile
Auth: Bearer JWT (seller)
Body: { business_name, business_category, address, phone, gst_number,
        fssai_license, bank_account_number, bank_ifsc }
Response 200: { "verification_status": "pending", "rejection_reason": null }
```

`PATCH /sellers/me/profile` always resets `verification_status` to `pending` and clears `rejection_reason`, triggering a fresh admin review.

### Admin verify

```
PATCH /sellers/admin/{seller_id}/verify
Auth: Bearer JWT (admin)
Body: { "action": "approve" }
  OR: { "action": "reject", "rejection_reason": "Missing valid FSSAI license" }

Response 200: {
  "seller_id": <int>,
  "verification_status": "approved" | "rejected",
  "rejection_reason": "<string>" | null
}
Response 400: action must be "approve" or "reject"; rejection_reason required when rejecting
Response 404: seller profile not found
```

`seller_id` is the `user.id` of the seller, not the `sellerprofile.id`.

---

## Frontend Wizard (`/seller/signup`)

A single-page 6-step wizard. Step state lives in `useState` — no router navigation between steps.

### Steps

| Step | Title | Fields | API call on Next |
|------|-------|--------|-----------------|
| 1 | Email | `email` | `POST /auth/otp/request` → advance to step 2 |
| 2 | Verify Code | `code` (6-digit) | `POST /auth/seller/otp/verify` → stores `emailToken`, advance to step 3 |
| 3 | Personal Info | `fullName`, `phone` | validate → advance to step 4 |
| 4 | Business Details | `businessName`, `businessCategory`, `address` | validate → advance to step 5 |
| 5 | Compliance & Bank | `gstNumber`, `fssaiLicense`, `bankAccountNumber`, `bankIfsc` | validate → advance to step 6 |
| 6 | Review & Submit | read-only summary with Edit links | `POST /auth/seller/register` → redirect to `/seller/signup/pending` |

### Client-side validation

Triggered on field `onBlur`, not on every keystroke.

| Field | Rule |
|-------|------|
| Phone | `/^[6-9]\d{9}$/` — 10-digit Indian mobile |
| GST number | `/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/` |
| IFSC code | `/^[A-Z]{4}0[A-Z0-9]{6}$/` |

### Token storage

After `POST /auth/seller/register` succeeds, the wizard saves `access_token` to `localStorage` under key `"kb_token"` before redirecting to `/seller/signup/pending`. This lets `AuthContext` hydrate with the new seller session on the next page load.

### Resubmit mode

URL: `/seller/signup?resubmit=true`

- Wizard starts at step 3 (email/OTP skipped — seller is already authenticated)
- Fields pre-filled by `GET /sellers/me/profile`
- `full_name` pre-filled from `dbUser.full_name` (AuthContext)
- Step 6 submits to `PATCH /sellers/me/profile` instead of `POST /auth/seller/register`
- After submit → same redirect to `/seller/signup/pending`

---

## Pending Page (`/seller/signup/pending`)

Shown after registration and after resubmit. Polls status every 30 seconds.

```
AuthContext hydrates from localStorage
       ↓
GET /sellers/me/status  (every 30s)
       ↓
  ┌─────────────┐
  │  pending    │ → Show hourglass, email, "1–2 business days"
  ├─────────────┤
  │  approved   │ → router.push("/seller")
  ├─────────────┤
  │  rejected   │ → Show rejection_reason callout
  │             │   + "Edit and resubmit" → /seller/signup?resubmit=true
  └─────────────┘
```

The polling interval is cleared on component unmount. A `cancelled` flag prevents state updates on stale callbacks.

---

## Seller Layout Guard (`/seller/layout.tsx`)

Protects all `/seller/*` routes except `/seller/signup/*`.

```
pathname.startsWith("/seller/signup")
  └─ true  → render children directly (no DashboardLayout, no checks)
  └─ false → apply guards:
       1. Role check: dbUser must exist and have role "seller"
          └─ fail → redirect to /login or /
       2. Verification check: GET /sellers/me/status
          └─ status !== "approved" → redirect to /seller/signup/pending
          └─ status === "approved" → render DashboardLayout with children
```

The signup routes are passed through without any wrapper or check because:
- Steps 1–2 of the wizard are accessed before the seller has an account
- The pending page is rendered outside the seller dashboard shell

---

## Admin Approval Workflow

1. Seller completes signup wizard → `SellerProfile.verification_status = "pending"`
2. Admin navigates to admin dashboard → sees list of pending sellers (Phase 5 UI, endpoint is live)
3. Admin calls `PATCH /sellers/admin/{seller_id}/verify` with `action: "approve"` or `"reject"`
4. On approval: seller's next poll of `/sellers/me/status` returns `"approved"` → redirect to `/seller`
5. On rejection: pending page shows `rejection_reason` callout + resubmit CTA

---

## Error Handling

| Scenario | Response | UI behaviour |
|----------|----------|--------------|
| OTP rate limited | 429 `rate_limited` | Toast: "Please wait N seconds…" |
| OTP invalid | 400 `invalid_code` | Toast: "Incorrect code" |
| OTP too many attempts | 429 `too_many_attempts` | Toast: "Too many attempts, request new code" |
| OTP / token expired | 410 `code_expired_or_used` | Toast: "Code expired" |
| Email token expired (10 min) | 400/410 `invalid/expired_email_token` | Toast: "Verification expired, start over" |
| Email already registered | 409 `email_already_registered` | Toast: "Already registered, log in instead" |
| Network / 5xx | any | Toast: "Something went wrong, please try again" |

---

## File Map

| File | Purpose |
|------|---------|
| `backend/app/src/app/models/seller.py` | `SellerProfile` SQLModel + `VerificationStatus` enum |
| `backend/app/src/app/core/security.py` | `create_email_verification_token`, `decode_email_verification_token` |
| `backend/app/src/app/api/auth.py` | `POST /auth/seller/otp/verify`, `POST /auth/seller/register` |
| `backend/app/src/app/api/sellers.py` | `GET /me/status`, `GET /me/profile`, `PATCH /me/profile`, `PATCH /admin/{id}/verify` |
| `backend/app/migrations/versions/d6342a56eaf6_*.py` | Alembic migration for `sellerprofile` table |
| `backend/app/tests/test_seller_register.py` | Registration endpoint tests |
| `backend/app/tests/test_seller_status.py` | Status/profile endpoint tests |
| `backend/app/tests/test_admin_verify.py` | Admin verify endpoint tests |
| `frontend/src/app/seller/signup/page.tsx` | 6-step wizard component |
| `frontend/src/app/seller/signup/seller-signup.module.css` | Wizard styles |
| `frontend/src/app/seller/signup/pending/page.tsx` | Pending approval page |
| `frontend/src/app/seller/signup/pending/pending.module.css` | Pending page styles |
| `frontend/src/app/seller/layout.tsx` | Seller layout with verification guard |
| `frontend/src/types/index.ts` | `SellerProfile`, `VerificationStatus` TypeScript types |
| `frontend/src/lib/api.ts` | `patch<T>()` helper added |
