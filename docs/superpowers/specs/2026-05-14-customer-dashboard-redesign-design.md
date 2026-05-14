# Customer Dashboard Redesign — Design

**Date:** 2026-05-14
**Branch (target):** `feat/customer-dashboard-redesign`
**Scope:** Refresh the customer `/account` area — separate sections, tabular orders, richer profile, supporting extras.

## Goals

- Replace the two-item nav (Orders + Settings) with a discrete-section sidebar (Dashboard, Orders, Addresses, Profile, Preferences, Support).
- Render orders in a sortable, filterable table instead of a card grid.
- Expand profile beyond name/phone/email — verification, stats, optional DOB, language preference, notification toggles.
- Add a useful dashboard landing (stats + active orders + reorder rail + recently viewed).
- Lift visual quality within the existing design-token system (no Tailwind).

## Non-goals (out of scope)

- Avatar upload (initials only).
- Sign-out-everywhere, account deletion, dark mode.
- Wishlist/favorites, notifications inbox, saved payment methods, loyalty wallet, refer-a-friend.
- One-click reorder endpoint (button routes to order detail where existing reorder action lives).
- Server-side order pagination.
- Per-address serviceability badge.

Each deferred item warrants its own spec.

## Rollout — three phases on one branch

Branch: `feat/customer-dashboard-redesign`. Each phase ships as a separate PR (merge-commit, branch retained per project workflow).

### Phase 1 — Frontend shell (no backend changes)

Mergeable on its own. Splits the existing settings page into discrete routes; nav grows to 6 items.

### Phase 2 — Orders table + dashboard landing widgets

Adds the new `/customers/me/stats` endpoint. Rewrites `/account` landing and `/account/orders`.

### Phase 3 — Profile + Preferences + Addresses polish + extras

Backend migration on `customer_profiles`, phone-OTP verification flow, order reviews table, support contact form, recently-viewed rail.

---

## Section 1 — Routes & sidebar nav

```
/account                       → Dashboard landing
/account/orders                → Orders table
/account/orders/[id]           → Order detail (existing; gains Rate button)
/account/addresses             → Addresses page
/account/profile               → Profile (identity + stats + verification)
/account/preferences           → Preferences (language + notifications)
/account/support               → Help & Support
```

`/account/settings` page becomes a redirect to `/account/profile`.

Sidebar items (in `frontend/src/app/(customer)/[locale]/account/layout.tsx`):

| Icon | Label key | Href |
|---|---|---|
| 🏠 | `navDashboard` | `/account` |
| 📦 | `navOrders` | `/account/orders` |
| 📍 | `navAddresses` | `/account/addresses` |
| 👤 | `navProfile` | `/account/profile` |
| ⚙️ | `navPreferences` | `/account/preferences` |
| 💬 | `navSupport` | `/account/support` |

Active match: `pathname === item.href` (existing). Page title selection driven by a route → translation-key map in the layout.

## Section 2 — Phase 1 (frontend shell)

**Files added:**

- `account/profile/page.tsx` + `page.module.css` — identity form moved out of settings (first/last name, phone, email, save). Same API: `GET /api/v1/customers/me`, `PATCH /api/v1/customers/me`.
- `account/addresses/page.tsx` + `page.module.css` — address grid + add/edit form moved out of settings. Same API.
- `account/preferences/page.tsx` — stub. Renders `LocaleSwitcher` only; real toggles in Phase 3.
- `account/support/page.tsx` — static FAQ + contact form; submission `console.log`s in Phase 1, wires to backend in Phase 3.

**Files modified:**

- `account/layout.tsx` — extend `customerNav` to the 6-item list; route → title map.
- `account/settings/page.tsx` — replace contents with `redirect("/account/profile")`.
- `messages/{en,hi,mr,gu,pa}.json` — new namespaces `Account.nav`, `Account.profile`, `Account.addresses`, `Account.preferences`, `Account.support`. Reuse existing settings keys where applicable.

**Risk:** stale in-app `/account/settings` deep links. Mitigated by the redirect.

**No frontend tests** (matches project convention).

## Section 3 — Phase 2 (orders table + dashboard landing)

### Orders table

Rewrite `account/orders/page.tsx` to use `components/DataTable.tsx`.

**Columns:**

| # | Key | Render |
|---|---|---|
| 1 | Order # | `#${id}`, monospace |
| 2 | Date | relative time, full timestamp on hover |
| 3 | Store | `store_name`, links to `/stores/${store_id}` |
| 4 | Service | `service_name`, chip |
| 5 | Items | `items.length` ("3 items") |
| 6 | Total | `₹{total.toFixed(2)}`, right-aligned |
| 7 | Payment | new `<PaymentStatusPill>` — method + paid/pending state |
| 8 | Status | existing `<OrderStatusBadge>` |
| 9 | Actions | kebab menu: View · Reorder (if delivered) · Cancel (if pending) · Rate (Phase 3, if delivered && no review) |

Row click → `/account/orders/${id}`.

**Controls strip (above table):**

- Status chips: All · Active (pending|packed|dispatched) · Delivered · Cancelled. Default: All.
- Service dropdown sourced from `GET /api/v1/catalog/services`.
- Optional date-range inputs.
- Search input — filters by order # or `store_name` (client-side).
- Sortable columns: Date, Total. Default `Date desc`.
- Pagination: 20-row "Load more" client-side slice.

**Mobile:** `DataTable.mobileCardRender` returns a compact card (#id · store · total · status).

### Dashboard landing

Rewrite `account/page.tsx`. CSS grid (1 column ≤ 720px, 2 columns above).

1. Greeting card — "Hi, {first_name} 👋" + today's date.
2. `<ActiveOrdersWidget />` (unchanged).
3. Stats strip — three `<StatsCard>`s: Orders this month · Lifetime spend · Favorite store. Fed by `/customers/me/stats`.
4. "Order again" rail — last 3 delivered orders rendered as compact cards linking to order detail.
5. "Recently viewed" rail (Phase 3) — last 5 viewed products from localStorage.

### Backend endpoint

`GET /api/v1/customers/me/stats` (customer-only).

```python
class OrderSummary(BaseModel):
    id: int
    store_id: int
    store_name: str
    service_id: int
    service_name: str
    total: float
    placed_at: datetime

class CustomerStatsResponse(BaseModel):
    orders_this_month: int
    lifetime_spend: float
    favorite_store_id: int | None
    favorite_store_name: str | None
    recent_delivered: list[OrderSummary]  # 3 most recent delivered orders, newest first
```

Implementation: new `services/customer_stats.py` aggregating over `Order` rows filtered by `customer_profile_id`. Favorite store = `store_id` with the most delivered orders for this customer (ties broken by most recent delivered order). Route in `api/customers.py`.

**Tests (backend):** `tests/test_customer_stats.py` — seed mixed orders for one customer; assert counts, spend, favorite store, recent list ordering, empty-state behavior (no orders → zeros, nulls, empty list).

## Section 4 — Phase 3a (profile + preferences)

### Alembic migration

```python
op.add_column("customer_profiles", sa.Column("date_of_birth", sa.Date(), nullable=True))
op.add_column("customer_profiles", sa.Column("preferred_language", sa.String(8), nullable=True))
op.add_column("customer_profiles", sa.Column("marketing_opt_in", sa.Boolean(), server_default=sa.text("false"), nullable=False))
op.add_column("customer_profiles", sa.Column("notify_order_email", sa.Boolean(), server_default=sa.text("true"), nullable=False))
op.add_column("customer_profiles", sa.Column("notify_order_sms", sa.Boolean(), server_default=sa.text("false"), nullable=False))
op.add_column("customer_profiles", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True))
```

`preferred_language` validated against the `LanguageCode` set (`en|hi|mr|gu|pa`) at the Pydantic layer.

### Backend changes

- `models/profile.py`: add new columns to `CustomerProfile`.
- `schemas/customers.py`: extend read schema; `CustomerProfileUpdate` accepts `date_of_birth`; new `CustomerPreferencesUpdate { preferred_language?, marketing_opt_in?, notify_order_email?, notify_order_sms? }`.
- `api/customers.py`:
  - `PATCH /customers/me` extended with `date_of_birth`.
  - New `PATCH /customers/me/preferences`.
- Phone-OTP verification (mirrors `/auth/seller/phone/otp/*`):
  - `POST /customers/me/phone/otp/request` — body `{ phone }`. Uses `core/otp.py` with namespace `otp:customer_phone:*`, rate-limit 5/hour, cooldown 60s. Strict E.164 validation before dispatch.
  - `POST /customers/me/phone/otp/verify` — body `{ phone, code }`. On success, set `phone_verified_at = utcnow()` and persist `phone`. Returns updated profile.

### Frontend

`account/profile/page.tsx`:

- Identity form: avatar chip (deterministic color from email hash, no upload), first_name, last_name, DOB (optional date input), email (readonly), phone (display + `Verify` button → modal OTP flow when `!phone_verified_at`).
- Verified badges: ✓ Email (always; OTP-only auth). ✓ Phone (when `phone_verified_at`).
- Stats card: Member since (from `created_at`), Total orders, Lifetime spend (reuses `/customers/me/stats`).
- Default address summary card with link to `/account/addresses`.

`account/preferences/page.tsx`:

- Language dropdown (en/hi/mr/gu/pa). Saving the form must also update local locale (LocaleSwitcher behavior) so the route locale follows.
- Notification toggles: order emails, order SMS, marketing emails.
- Save → `PATCH /customers/me/preferences`.

New components:

- `components/PhoneVerifyModal.tsx` — `<Modal>` wrapping the two-step OTP flow.

### Tests (backend)

- `tests/test_customer_preferences.py` — PATCH happy path, invalid `preferred_language` → 422, partial update preserves untouched fields.
- `tests/test_customer_phone_verification.py` — request → verify → `phone_verified_at` set; wrong OTP → 422; rate limit beyond 5/hour → 429; verifying with a different number than requested → 400.

## Section 5 — Phase 3b (addresses polish + extras)

### Addresses page

`account/addresses/page.tsx`:

- Card shows: label, formatted address, **DIGIPIN** (mono font), **lat,lng** muted text, default badge, action row (Edit · Set default · View on map · Delete).
- "View on map" → `<Modal>` containing `<MapPicker>` read-only, centered on address coords.
- Add-address form: "Use current location" button → `navigator.geolocation.getCurrentPosition` → populates lat/lng → calls existing `GET /api/v1/geo/reverse` to backfill street/city/state/pincode.

No backend changes.

### Order rating + review

**Backend migration:** new `order_reviews` table.

```python
op.create_table(
    "order_reviews",
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), unique=True, nullable=False),
    sa.Column("customer_profile_id", sa.Integer(), sa.ForeignKey("customer_profiles.id", ondelete="CASCADE"), nullable=False),
    sa.Column("rating", sa.SmallInteger(), nullable=False),  # 1..5
    sa.Column("comment", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
)
```

**Backend:**

- `models/commerce.py` — `OrderReview` SQLModel.
- Schemas: `OrderReviewCreate { rating: int, comment: str | None }`, `OrderReviewRead`.
- Routes in `api/orders.py`:
  - `POST /orders/{id}/review` — customer-only.
    - 404 if not owned, 409 if `status != "delivered"` or a review already exists, 422 if rating out of range.
  - `GET /orders/{id}` response extended with `review: OrderReviewRead | null` for the owning customer (visible only to owner).

**Frontend:**

- `components/orders/OrderActionButtons.tsx` — "Rate order" button when `order.status === "delivered" && order.review === null`.
- New `components/orders/OrderReviewForm.tsx` — 5-star input + comment textarea + submit. Renders inline on order detail and as a Modal trigger from the orders-table kebab.
- Orders-table "Rate" action item gated the same way.

**Tests (backend):** `tests/test_order_reviews.py` — happy path; not-delivered → 409; duplicate → 409; not-owner → 404; rating <1 or >5 → 422; `GET /orders/{id}` returns review when present.

### Help & Support

**Backend:**

- New `POST /api/v1/customers/me/support` — body `{ subject, message }`. Dispatches a Celery email task to `settings.SUPPORT_EMAIL` (new env var, defaults to `support@khanabazaar.example` in dev). Reuses `core/email.py` + the existing OTP/order email patterns in `worker.py`. No DB persistence in MVP.

**Frontend:**

- `account/support/page.tsx` — static FAQ (5–8 entries, translated) + contact form (subject, message). Posts to `/customers/me/support`, success toast on 200.

### Recently viewed products

Pure client-side.

- New hook `lib/recentlyViewed.ts` — read/write `localStorage` key `kb_recently_viewed` (JSON array of `{ product_id, store_id, name, image_url, viewed_at }`, capped at 20, deduped by `product_id`).
- `ProductDetail` mount pushes the current product.
- Rendered as a `<RecentlyViewedRail>` on `/account` (below "Order again") when array non-empty. Tap → `/stores/{store_id}/products/{product_id}`.

No backend.

## Section 6 — Visual styling & component hygiene

- All new pages use CSS Modules + tokens from `frontend/src/styles/design-tokens.css`. No inline layout styles (clean up the existing `account/page.tsx` block in Phase 2).
- Page-level layout: `max-width: 1120px`, content gap `24px`, section cards with `--shade-cool-light-0` background, `--shade-cool-light-2` border, 12px radius, subtle `0 1px 2px rgba(0,0,0,.04)` shadow.
- Section header: 18–20px semibold title + 13px muted subtitle + right-aligned primary action.
- Reused as-is: `DashboardLayout`, `DataTable`, `StatsCard`, `Modal`, `MapPicker`, `AddressFields`, `OrderStatusBadge`, `ActiveOrdersWidget`.
- Touched: `OrderActionButtons` (add Rate), `LocaleSwitcher` (writes both `localStorage` and the persisted server preference for logged-in users).
- New components: `EmptyState`, `PaymentStatusPill`, `OrderReviewForm`, `PhoneVerifyModal`, `RecentlyViewedRail`, `OrderAgainRail`, `StatsStrip`.
- Mobile: sidebar collapses via existing toggle. Tables use `mobileCardRender`. Forms stack to one column ≤ 720px.

### i18n

- New namespaces: `Account.nav`, `Account.dashboard`, `Account.profile`, `Account.addresses`, `Account.preferences`, `Account.support`, `Account.orders.table`, `Order.review`.
- English authored first; hi/mr/gu/pa land as English placeholders if translators not in loop (matches existing repo convention).

### Lint / types gates per phase

- Frontend: `npm run lint` and `tsc --noEmit` clean before merge.
- Backend: `uv run ruff check .`, `uv run mypy .`, `uv run pytest -v` clean before merge.

## Section 7 — Error handling, risks

### Error handling

- All new fetches go through `lib/api.ts` (`ApiError` + `apiErrorKey`); localized errors render through the existing banner pattern from `account/settings/page.tsx`.
- Phone-OTP modal: 429 → "Try again in {n}s"; 422 → field-level error; expired token → reopen modal at step 1.
- Stats endpoint failure: dashboard renders without the stats strip (silent fallback + console log). Active-orders and Order-again rails render independently.
- Recently-viewed: localStorage parse error → reset the key, render empty rail.
- Review submission: 409 → inline message + disable form.
- Geolocation denied: "Use current location" shows a hint; form still works manually.

### Risks / gotchas

- **i18n catch-up:** 5 languages × many keys. English first; others fall back to English strings until translated.
- **`preferred_language` UX:** when set, it should override the URL locale on first navigation for logged-in users. `LocaleSwitcher` must persist both client-side and to the server.
- **Strict E.164 phone validation** required before dispatching OTP (mirrors seller flow). Existing customer-profile phone regex is permissive; tighten on the verify path only.
- **Review gating:** reviews only on `delivered`. Spec the 409 path so tests cover it.
- **Stats query cost:** fine at MVP scale. If it gets slow, materialize a `customer_stats` row updated by a Celery task on order state change.
- **Stale `/account/settings` deep links:** in-app links handled by server-side `redirect()`; external bookmarks transparently land on `/account/profile`.

## Approval

Approach: layered 3-phase rollout on `feat/customer-dashboard-redesign`, each phase a separate merge-commit PR.
