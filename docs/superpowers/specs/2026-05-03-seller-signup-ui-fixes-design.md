<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Seller Signup UI Fixes & Optional Compliance Fields

**Date:** 2026-05-03
**Branch:** feat/seller-services (or new branch from main)
**Author:** brainstorming session

## Problem

Two issues observed on the seller signup wizard (`/seller/signup`):

1. **Step 4 layout bug.** "Business name" and "Services Offered" share a 2-column CSS grid (`.formGrid` at `min-width: 480px`). The single-line text input collapses into a narrow ~25%-width column while the multi-card `ServicePicker` stretches across the rest. Result on mid-narrow viewports: the input shows as `[Sha|`, the placeholder is clipped, and the "Business name is required" error wraps to four lines. Visual hierarchy is broken; mobile and tablet are both affected.

2. **Compliance fields blocking signup.** Step 5 currently requires `fssaiLicense`, `bankAccountNumber`, and `bankIfsc` to be non-empty before the seller can advance to review. Many legitimate sellers (especially non-food categories like Electronics or Pharmacy where compliance regimes differ) cannot or should not be forced to provide these at signup. Admin approval is the gate for verification; signup must collect these fields opportunistically, not coercively.

## Goals

- Restore a readable, mobile-first layout for Step 4 across all viewport widths.
- Make GST, FSSAI, bank account number, and IFSC code optional at every layer (frontend validation, request schema, ORM model, database column).
- Keep format validation in place when those fields **are** filled (GST regex, IFSC regex).
- No functional change to other steps. No change to admin verification flow.

## Non-Goals

- Redesigning the wizard step model or the visual identity of the page.
- Adding new compliance field types (PAN, MSME registration, etc.).
- Changing how admin reviews or approves sellers.
- Localization or i18n changes.

## Design

### Frontend — Step 4 layout

**Current structure (page.tsx, outer wrapper at line 532, blocks span ~535–591):**

```tsx
<div className={styles.formGrid}>
  <div className={styles.inputGroup}>{/* Business name */}</div>
  <div className={styles.formGroup}>{/* ServicePicker */}</div>
  <div className={`${styles.inputGroup} ${styles.formGridFull}`}>
    {/* Address fields */}
  </div>
</div>
```

**New structure:** drop the `.formGrid` wrapper for Step 4 and let each block occupy its own full-width row inside the existing `.form` flex column. Also drop `.formGridFull` from the address block — that class only sets `grid-column: 1 / -1` and becomes dead once the parent grid is gone.

```tsx
<>
  <div className={styles.inputGroup}>{/* Business name, full-width */}</div>
  <div className={styles.formGroup}>{/* ServicePicker, full-width */}</div>
  <div className={styles.inputGroup}>{/* Address fields */}</div>
</>
```

`ServicePicker` already has its own internal responsive grid (1 col mobile → 2 col ≥640px → 3 col ≥1024px). Removing the outer `.formGrid` wrapper means the picker fills the row and the cards remain comfortably sized at every breakpoint.

No CSS changes required for `.formGrid` itself; it's still used by other steps. But verify Step 3 (Personal Info) still uses it correctly (`fullName` + `phone` two-column at ≥480px) — it should remain unchanged.

### Frontend — Step 5 validation

File: `frontend/src/app/seller/signup/page.tsx` (validation block around lines 783–800).

Current checks:

```ts
if (gstNumber && !GST_REGEX.test(gstNumber)) errs.gstNumber = "...";
if (!fssaiLicense.trim()) errs.fssaiLicense = "FSSAI license number is required";
if (!bankAccountNumber.trim()) errs.bankAccountNumber = "Bank account number is required";
if (bankIfsc && !IFSC_REGEX.test(bankIfsc)) errs.bankIfsc = "...";
```

New checks:

```ts
if (gstNumber && !GST_REGEX.test(gstNumber)) errs.gstNumber = "...";
// FSSAI: optional, no format regex available — accept any non-empty trimmed value
if (bankAccountNumber && !/^\d{9,18}$/.test(bankAccountNumber)) {
  errs.bankAccountNumber = "Enter a valid bank account number (9–18 digits)";
}
if (bankIfsc && !IFSC_REGEX.test(bankIfsc)) errs.bankIfsc = "...";
```

All four fields become advance-able when blank. Format validation only fires when the user has typed something.

Label updates (in JSX around the relevant inputs):

- `GST Number` → `GST Number (optional)`
- `FSSAI License` → `FSSAI License (optional)`
- `Bank Account Number` → `Bank Account Number (optional)`
- `Bank IFSC Code` → `Bank IFSC Code (optional)`

This matches the existing pattern used on `Address line 2 (optional)` (Step 4).

### Backend — schema

File: `backend/app/src/app/schemas/sellers.py`. Four BaseModel subclasses define `bank_account_number: str` / `bank_ifsc: str` (lines 25-26, 37-38, 51-52, 67-68). Change all four to:

```python
bank_account_number: Optional[str] = None
bank_ifsc: Optional[str] = None
```

GST and FSSAI are already `Optional[str] = None` — no change.

### Backend — model

File: `backend/app/src/app/models/profile.py` lines 73-74:

```python
# Before
bank_account_number: str = Field(nullable=False)
bank_ifsc: str = Field(nullable=False)

# After
bank_account_number: Optional[str] = Field(default=None)
bank_ifsc: Optional[str] = Field(default=None)
```

### Backend — Alembic migration

New revision: `make_bank_fields_nullable_on_seller_profile`.

```python
def upgrade() -> None:
    op.alter_column(
        "sellerprofile", "bank_account_number",
        existing_type=sa.String(), nullable=True,
    )
    op.alter_column(
        "sellerprofile", "bank_ifsc",
        existing_type=sa.String(), nullable=True,
    )

def downgrade() -> None:
    op.alter_column(
        "sellerprofile", "bank_ifsc",
        existing_type=sa.String(), nullable=False,
    )
    op.alter_column(
        "sellerprofile", "bank_account_number",
        existing_type=sa.String(), nullable=False,
    )
```

Downgrade will fail on existing rows with NULL values; that is acceptable — migrations roll forward in this project.

### Backend — endpoints

`api/auth.py` (signup) and `api/sellers.py` (update) already pass `body.bank_account_number` / `body.bank_ifsc` straight into the ORM. With schemas allowing `None` and the model accepting `None`, no logic change is needed in either route.

### Mobile responsiveness audit

After the Step 4 change, manually verify the following at 320px, 375px, 414px, 768px, 1024px viewport widths:

- Wizard card padding does not crush content on 320px.
- Step 3 (`fullName` + `phone`) still uses 2-col layout above 480px and stacks below.
- Step 4 Business name input takes full width and matches Address line 1 visually.
- Step 4 ServicePicker shows 1 col below 640px, 2 col at 640–1023px, 3 col at ≥1024px.
- Step 5 inputs all full-width and labels show "(optional)" suffix.
- Step header title "Sell on KhanaBazaar" does not overflow on 320px.

## Testing

**Backend:**

- Existing seller signup test (`backend/app/tests/test_seller_register.py`) should still pass.
- Add one new test case in `test_seller_register.py`: POST the seller register endpoint with `gst_number=None`, `fssai_license=None`, `bank_account_number=None`, `bank_ifsc=None` returns 200 and creates a `SellerProfile` row with NULLs in those columns.
- Run `uv run pytest -v` and `uv run mypy .` from `backend/app/`.

**Frontend:**

- No unit-test infrastructure exists for the signup wizard. Manual verification:
  1. Run `npm run dev` and open `http://localhost:3000/seller/signup`.
  2. Walk through steps 1-4 with valid input. Confirm Step 4 layout is fixed at desktop and mobile widths (use Chrome DevTools device emulation).
  3. On Step 5, leave all four compliance fields blank and click Next. Confirm advance succeeds.
  4. On Step 5, type an invalid IFSC (`HDFC1234567`) and confirm format error still blocks advance.
  5. On Step 5, type a valid IFSC and submit. Confirm wizard reaches Step 6 review and submission succeeds.
- `npm run lint` from `frontend/` must pass.

## Rollout

1. Single PR against `main`.
2. Migration runs on next deploy via existing Alembic step.
3. No feature flag — change is purely additive (loosens constraints).
4. Existing seller profiles unaffected; their bank fields remain populated.

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/app/seller/signup/page.tsx` | Step 4 JSX restructure; Step 5 validation loosening; "(optional)" labels |
| `backend/app/src/app/schemas/sellers.py` | `bank_account_number` / `bank_ifsc` → `Optional[str]` in 4 models |
| `backend/app/src/app/models/profile.py` | `bank_account_number` / `bank_ifsc` → `Optional[str]`, `Field(default=None)` |
| `backend/app/migrations/versions/<new>.py` | New migration: drop NOT NULL on the two columns |
| `backend/app/tests/test_seller_register.py` | Add nullable-bank-fields test case |

No CSS file changes required. `seller-signup.module.css` keeps its `.formGrid` rules for use by Step 3.
