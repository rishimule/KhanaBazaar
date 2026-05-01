# Customer Account Settings — Design

**Date:** 2026-05-01
**Status:** Draft
**Scope:** Add a customer account area with `/account/settings` as the first page. Customers can view and update basic profile details and manage saved delivery addresses.

## Motivation

Customers can sign in and shop, but they do not yet have a place to manage account details outside checkout. The platform already has `CustomerProfile`, `CustomerAddress`, and reusable structured address UI. This feature turns those foundations into a customer-facing account settings experience.

The first version should stay focused:

- Give customers a stable home for account settings.
- Let customers update their name and phone number.
- Show email as a read-only account identifier.
- Let customers add, edit, delete, and choose a default delivery address.
- Establish an `/account` route structure that can later host order history and support pages.

## Scope

In scope:

- Customer-only `/account` route area.
- `/account/settings` page as the first customer account page.
- Profile view/edit for first name, last name, and phone.
- Read-only email display.
- Saved address list.
- Add, edit, delete, and set-default address actions.
- Backend customer profile/address APIs.
- Backend tests for profile/address behavior and access control.
- Frontend lint/build verification.

Out of scope:

- Order history.
- Payment methods.
- Notification preferences.
- Password management, because auth uses email OTP.
- Phone OTP verification.
- Address geocoding, delivery radius validation, or map picker.
- Checkout integration changes. Future checkout work will reuse the saved-address API from this feature.

## Recommended Approach

Use an account dashboard shell now, but ship only one real page: `/account/settings`.

This avoids a throwaway standalone settings route while keeping the first implementation small. The account area can later add `/account/orders`, `/account/support`, or `/account/favorites` without changing the navigation pattern.

Rejected alternatives:

- Standalone `/account/settings` with no shell: fastest, but creates a dead-end page that will need restructuring when customer account features expand.
- Full multi-page account area now: cleaner long-term information architecture, but unnecessary before order history and support pages exist.

## Information Architecture

Routes:

- `/account` redirects to `/account/settings`.
- `/account/settings` renders the customer settings page.

Navigation:

- Initial account nav contains only `Settings`.
- The layout must support adding future `Orders`, `Favorites`, and `Support` links without adding placeholder pages in this feature.

Access rules:

- Guests are redirected to `/login`.
- Signed-in customers can access `/account`.
- Signed-in admins and sellers are redirected away from `/account`.

Recommended non-customer redirects:

- Admins: `/admin`.
- Sellers: `/seller`.
- Any other unexpected role: `/`.

## Backend API

Add a customer-focused router mounted under `/api/v1/customers`.

### Endpoints

`GET /api/v1/customers/me`

Returns the current customer's profile and saved addresses.

`PATCH /api/v1/customers/me`

Updates profile fields. Accepted fields:

- `first_name`
- `last_name`
- `phone`

Email is not editable through this endpoint.

`POST /api/v1/customers/me/addresses`

Creates a new saved address for the current customer.

`PUT /api/v1/customers/me/addresses/{customer_address_id}`

Updates an existing saved address owned by the current customer. This is a full address replacement for the nested address object plus editable metadata:

- `label`
- `is_default`
- `address`

`DELETE /api/v1/customers/me/addresses/{customer_address_id}`

Deletes an address owned by the current customer.

`POST /api/v1/customers/me/addresses/{customer_address_id}/default`

Marks one owned address as the default and clears default status from all other addresses for the customer.

### Response Shape

The profile response should be explicit and frontend-friendly:

```json
{
  "user_id": 12,
  "email": "customer@example.com",
  "first_name": "Asha",
  "last_name": "Patel",
  "phone": "9876543210",
  "addresses": [
    {
      "id": 4,
      "label": "Home",
      "is_default": true,
      "address": {
        "address_line1": "12 MG Road",
        "address_line2": "Apt 4B",
        "landmark": "Near metro station",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400001",
        "country": "India",
        "latitude": null,
        "longitude": null
      }
    }
  ]
}
```

### Backend Rules

- Resolve the customer from the JWT with the existing auth dependency.
- Require `UserRole.Customer`.
- Resolve `CustomerProfile` by `user_id`.
- If a customer user exists without a `CustomerProfile`, return `404` with `{"detail": "Customer profile not found"}`. Current OTP signup should already create the profile, so silent repair is out of scope for v1.
- Enforce address ownership through `CustomerAddress.customer_profile_id`.
- Use the existing `AddressPayload` schema and address conversion helpers.
- When an address is made default, unset all other defaults for that customer in the same transaction.
- When deleting the default address, leave the customer with no default address. Do not auto-promote another address in v1.
- All profile and address mutation endpoints return the full customer profile response, so the frontend can refresh state without an extra fetch.

## Frontend Design

### Account Layout

Add `frontend/src/app/account/layout.tsx`.

Behavior:

- Client component because it uses `useAuth`, `useRouter`, and route guarding.
- Redirects guests to `/login`.
- Redirects non-customers as described above.
- Wraps account pages in a dashboard shell.

The existing `DashboardLayout` currently accepts only `seller` and `admin`. The implementation can either:

- Generalize `DashboardLayout` to support `customer`, or
- Create a focused customer account layout with the same visual conventions.

Preferred implementation: generalize `DashboardLayout` if the change stays small. A single dashboard shell is easier to keep consistent across roles.

### Settings Page

Add `frontend/src/app/account/settings/page.tsx` and a page-specific CSS module.

Page content:

- Header: `Account settings`.
- Signed-in email shown as account identity.
- Profile section with editable first name, last name, and phone.
- Email field displayed read-only.
- Saved addresses section with address cards.
- Add/edit address form using existing `AddressFields`.
- Delete confirmation before removing an address.

Layout guidance:

- Use a dense, practical dashboard layout.
- Do not use a marketing-style hero.
- Keep profile and address sections on one page for v1.
- Cards are appropriate for individual saved addresses.
- Avoid nesting cards inside cards.
- Use existing design tokens and CSS Modules.
- Keep mobile forms single-column and desktop forms two-column where space allows.

### Address Interactions

Address card:

- Label, falling back to `Address`.
- Default badge when `is_default` is true.
- Formatted address from `formatAddress`.
- Actions: edit, set default, delete.

Add/edit form:

- Reuse `AddressFields`.
- Include a label input, for example `Home`, `Work`, or `Family`.
- Include a default-address checkbox.
- Keep the form open on mutation failure.
- Disable submit while saving.

Empty state:

- Compact message that no delivery addresses are saved.
- Primary action to add an address.

## Frontend Types

Extend `frontend/src/types/index.ts`:

```ts
export interface CustomerAddress {
  id: number;
  label: string | null;
  is_default: boolean;
  address: Address;
}

export interface CustomerProfile {
  user_id: number;
  email: string;
  first_name: string;
  last_name: string | null;
  phone: string | null;
  addresses: CustomerAddress[];
}
```

Request types can live near the settings page unless they are shared elsewhere.

## Data Flow

Initial load:

1. `/account/settings` reads `token` from `useAuth`.
2. Page calls `GET /api/v1/customers/me`.
3. Page stores profile and address data locally.

Profile save:

1. User edits first name, last name, or phone.
2. Page submits `PATCH /api/v1/customers/me`.
3. Page updates local profile from the response.

Address create/update/delete/default:

1. User performs an address action.
2. Page calls the matching customer address endpoint.
3. Page updates local profile/address state from the response.

No optimistic writes are required in v1. The UI should update after successful API responses.

## Validation And Error Handling

Frontend:

- Require first name.
- Treat last name and phone as optional.
- Keep email read-only.
- Use basic phone length/character validation in the form, but rely on backend validation as the source of truth.
- Reuse existing `AddressFields` validation affordances.
- Show field-level errors when the backend returns validation details that can be mapped.
- Show a section-level error for unexpected API failures.
- Keep unsaved address form input after failed create/update.

Backend:

- Return `401` for missing/invalid auth.
- Return `403` for authenticated non-customer users.
- Return `404` for address IDs not owned by the current customer.
- Return `422` for invalid profile/address payloads.
- Keep default-address changes transactional.

Destructive action:

- Address delete requires a confirmation in the UI.

## Testing

### Backend

Add focused tests for the customer router:

- Guest cannot access `GET /customers/me`.
- Seller/admin cannot access customer endpoints.
- Customer can fetch their profile.
- Customer can update first name, last name, and phone.
- Customer cannot update email through profile endpoint.
- Customer can add an address.
- Invalid address payload returns `422`.
- Customer can edit an owned address.
- Customer cannot edit/delete another customer's address.
- Customer can set a default address.
- Setting one default clears previous defaults.
- Deleting a default address leaves no default address.
- Deleting a non-owned address returns `404`.

Use existing test patterns from auth/stores/seller tests, including dependency overrides.

### Frontend

Minimum verification:

- `npm run lint`
- `npm run build`

Manual test plan:

1. Sign in as a customer.
2. Visit `/account` and confirm redirect to `/account/settings`.
3. Edit first name, last name, and phone.
4. Add a delivery address.
5. Edit the address.
6. Set the address as default.
7. Add a second address and set it as default; verify the first loses default status.
8. Delete the default address; verify no default remains.
9. Confirm guest access redirects to `/login`.
10. Confirm seller/admin users cannot access `/account/settings`.

## Implementation Boundaries

Backend files likely involved:

- `backend/app/src/app/api/__init__.py`
- `backend/app/src/app/api/customers.py`
- `backend/app/src/app/schemas/customers.py`
- `backend/app/tests/test_customers.py`

Frontend files likely involved:

- `frontend/src/app/account/layout.tsx`
- `frontend/src/app/account/page.tsx`
- `frontend/src/app/account/settings/page.tsx`
- `frontend/src/app/account/settings/page.module.css`
- `frontend/src/components/DashboardLayout.tsx`
- `frontend/src/components/DashboardLayout.module.css`
- `frontend/src/types/index.ts`

Avoid unrelated refactors. Existing seller/admin dashboards should continue to render as they do now.

## Rollout

- No database migration is expected because the required customer profile/address tables already exist.
- No environment variable changes.
- No feature flag required.
- This can ship before checkout address selection integration; checkout can adopt saved addresses later.

## Open Questions

None. The first version is intentionally limited to editable name/phone, read-only email, and saved address management.
