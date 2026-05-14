# Customer Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the customer `/account` area into discrete sections (Dashboard, Orders, Addresses, Profile, Preferences, Support), render orders in a sortable/filterable table, enrich profile with verification + stats, add order reviews + help form + recently-viewed.

**Architecture:** Three sequential phases on `feat/customer-dashboard-redesign`, each merged via its own merge-commit PR (branch retained per project workflow). Phase 1 is frontend-only routing/scaffolding. Phase 2 adds the orders table + dashboard widgets + one new aggregate endpoint. Phase 3 adds the customer-profile migration, preferences/phone-verification/order-review/support endpoints, and the corresponding frontend pages and components.

**Tech Stack:** Next.js 16 App Router (CSS Modules + `design-tokens.css`, no Tailwind), FastAPI 0.135 + SQLModel + Alembic + asyncpg, PyJWT, Redis-backed OTP, Celery 5.6 for email tasks, Pytest + pytest-asyncio against `khanabazaar_test` (real Postgres).

**Reference spec:** `docs/superpowers/specs/2026-05-14-customer-dashboard-redesign-design.md`.

**Branch:** Create from latest `main`:
```bash
git checkout main && git pull && git checkout -b feat/customer-dashboard-redesign
```

---

## Part 1 — Frontend shell (no backend changes)

### Task 1.1: Extend customer sidebar to six items

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/account/layout.tsx`

- [ ] **Step 1: Replace `customerNav` and `title` selection**

Replace the `customerNav` array (currently 2 items) and the `title` ternary with the 6-item nav and a route → translation-key map. New `layout.tsx` body (replacing the existing return):

```tsx
const customerNav = [
  { href: "/account", label: t("navDashboard"), icon: "🏠" },
  { href: "/account/orders", label: t("navOrders"), icon: "📦" },
  { href: "/account/addresses", label: t("navAddresses"), icon: "📍" },
  { href: "/account/profile", label: t("navProfile"), icon: "👤" },
  { href: "/account/preferences", label: t("navPreferences"), icon: "⚙️" },
  { href: "/account/support", label: t("navSupport"), icon: "💬" },
];

const PAGE_TITLE_KEY: Record<string, string> = {
  "/account": "layoutTitle",
  "/account/orders": "layoutOrdersTitle",
  "/account/addresses": "layoutAddressesTitle",
  "/account/profile": "layoutProfileTitle",
  "/account/preferences": "layoutPreferencesTitle",
  "/account/support": "layoutSupportTitle",
};

const title = t(PAGE_TITLE_KEY[pathname] ?? "layoutTitle");
```

- [ ] **Step 2: Add nav + title translation keys to all five message files**

Edit `frontend/messages/{en,hi,mr,gu,pa}.json`. Under the existing `Account` object, add (English example; copy verbatim into hi/mr/gu/pa for now — placeholder English fallbacks are the repo convention):

```json
"navDashboard": "Dashboard",
"navOrders": "Orders",
"navAddresses": "Addresses",
"navProfile": "Profile",
"navPreferences": "Preferences",
"navSupport": "Support",
"layoutTitle": "Dashboard",
"layoutOrdersTitle": "Orders",
"layoutAddressesTitle": "Addresses",
"layoutProfileTitle": "Profile",
"layoutPreferencesTitle": "Preferences",
"layoutSupportTitle": "Help & Support",
```

The existing keys `navOrders`, `navSettings`, `layoutSettingsTitle` stay for now (cleanup in Task 1.6).

- [ ] **Step 3: Type-check + lint**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```
Expected: no errors. If `navOrders` already exists in `Account` namespace, dedupe rather than throw a parse error.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\(customer\)/\[locale\]/account/layout.tsx frontend/messages
git commit -m "feat(account): expand customer dashboard sidebar to six sections"
```

---

### Task 1.2: Profile page (identity form split out of settings)

**Files:**
- Create: `frontend/src/app/(customer)/[locale]/account/profile/page.tsx`
- Create: `frontend/src/app/(customer)/[locale]/account/profile/page.module.css`

- [ ] **Step 1: Create `page.module.css`**

Copy the styling shape from `account/settings/page.module.css` but keep only the rules used by the identity form: `.page`, `.loading`, `.section`, `.sectionHeader`, `.sectionTitle`, `.sectionSubtitle`, `.profileForm`, `.field`, `.label`, `.input`, `.inputError`, `.errorText`, `.formActions`, `.errorBanner`.

- [ ] **Step 2: Create `page.tsx`**

Lift the profile half of `account/settings/page.tsx` (the `profile`/`profileForm` state, `saveProfile` handler, and the `<section>` for "profileSection") into a standalone client component. Drop all address-related state and effects. Use `useTranslations("Account.profile")` (new namespace) for keys; copy the relevant strings from `Account.settings` into `Account.profile` in all message files.

Endpoints used (unchanged): `GET /api/v1/customers/me`, `PATCH /api/v1/customers/me`.

- [ ] **Step 3: Add `Account.profile.*` keys to all message files**

In `frontend/messages/{en,hi,mr,gu,pa}.json`, add an `Account.profile` block with:

```json
"profile": {
  "loading": "Loading profile…",
  "loadError": "Could not load your profile.",
  "saveProfileError": "Could not save changes.",
  "profileSection": "Profile",
  "firstNameLabel": "First name",
  "lastNameLabel": "Last name",
  "phoneLabel": "Phone",
  "emailLabel": "Email",
  "firstNameRequired": "First name is required.",
  "phoneInvalid": "Enter a valid phone number.",
  "saveProfile": "Save changes",
  "saving": "Saving…"
}
```

- [ ] **Step 4: Type-check + lint**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```
Expected: clean.

- [ ] **Step 5: Manual smoke**

Run `./scripts/dev.sh start`, log in as a customer, navigate to `http://localhost:3000/en/account/profile`. Expected: identity form renders pre-filled, save persists, sidebar highlights "Profile".

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/\(customer\)/\[locale\]/account/profile frontend/messages
git commit -m "feat(account): add /account/profile page (identity form split)"
```

---

### Task 1.3: Addresses page (address book split out of settings)

**Files:**
- Create: `frontend/src/app/(customer)/[locale]/account/addresses/page.tsx`
- Create: `frontend/src/app/(customer)/[locale]/account/addresses/page.module.css`

- [ ] **Step 1: Create `page.module.css`**

Copy from `account/settings/page.module.css` only the address-related selectors: `.page`, `.loading`, `.section`, `.sectionHeader`, `.sectionTitle`, `.sectionSubtitle`, `.errorBanner`, `.addressGrid`, `.addressCard`, `.addressCardHeader`, `.addressLabel`, `.defaultBadge`, `.addressText`, `.addressActions`, `.textButton`, `.dangerButton`, `.addressForm`, `.addressFormHeader`, `.addressFormTitle`, `.field`, `.label`, `.input`, `.checkboxRow`, `.formActions`, `.emptyState`.

- [ ] **Step 2: Create `page.tsx`**

Lift the addresses half of `account/settings/page.tsx` — `addressForm`, `addressErrors`, `busyAddressId`, `sortedAddresses`, and the `openNewAddressForm`/`editAddress`/`saveAddress`/`setDefaultAddress`/`deleteAddress` handlers — into a standalone client component. Drop the profile form. Use `useTranslations("Account.addresses")`. Endpoints unchanged: `POST/PUT/DELETE /api/v1/customers/me/addresses/:id`, `POST .../default`.

- [ ] **Step 3: Add `Account.addresses.*` keys**

In `frontend/messages/{en,hi,mr,gu,pa}.json`, add an `Account.addresses` block (move the address-related keys from the existing `Account.settings` namespace verbatim — `addressesTitle`, `addressCount`, `addAddress`, `noAddresses`, `addressFallbackLabel`, `defaultBadge`, `edit`, `setDefault`, `delete`, `deleteFallbackLabel`, `deleteConfirm`, `addAddressFormTitle`, `editAddressFormTitle`, `labelLabel`, `labelPlaceholder`, `makeDefault`, `saveAddress`, `saveAddressError`, `setDefaultError`, `deleteAddressError`, `cancel`, `saving`, `loading`, `loadError`).

- [ ] **Step 4: Type-check + lint**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(customer\)/\[locale\]/account/addresses frontend/messages
git commit -m "feat(account): add /account/addresses page (address book split)"
```

---

### Task 1.4: Preferences page (stub)

**Files:**
- Create: `frontend/src/app/(customer)/[locale]/account/preferences/page.tsx`
- Create: `frontend/src/app/(customer)/[locale]/account/preferences/page.module.css`

- [ ] **Step 1: Create `page.module.css`** (minimal — reuse settings panel look)

```css
.page { display: flex; flex-direction: column; gap: var(--space-6); max-width: var(--container-lg); }
.section { background: var(--color-neutral-0); border: 1px solid var(--color-neutral-100); border-radius: var(--radius-md); padding: var(--space-5); }
.title { font-size: var(--font-xl); font-weight: var(--weight-semibold); color: var(--color-neutral-900); margin-bottom: var(--space-2); }
.subtitle { font-size: var(--font-sm); color: var(--color-neutral-500); margin-bottom: var(--space-4); }
.empty { color: var(--color-neutral-500); font-size: var(--font-sm); }
```

- [ ] **Step 2: Create `page.tsx`** as a stub that renders only the existing `LocaleSwitcher`

```tsx
"use client";
import { useTranslations } from "next-intl";
import LocaleSwitcher from "@/components/LocaleSwitcher";
import styles from "./page.module.css";

export default function PreferencesPage() {
  const t = useTranslations("Account.preferences");
  return (
    <div className={styles.page}>
      <section className={styles.section}>
        <h2 className={styles.title}>{t("languageTitle")}</h2>
        <p className={styles.subtitle}>{t("languageSubtitle")}</p>
        <LocaleSwitcher />
      </section>
      <section className={styles.section}>
        <h2 className={styles.title}>{t("notificationsTitle")}</h2>
        <p className={styles.empty}>{t("notificationsComingSoon")}</p>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Add `Account.preferences.*` keys**

Add to `frontend/messages/{en,hi,mr,gu,pa}.json` under `Account`:

```json
"preferences": {
  "languageTitle": "Language",
  "languageSubtitle": "Choose the language for your dashboard.",
  "notificationsTitle": "Notifications",
  "notificationsComingSoon": "Notification preferences coming soon."
}
```

- [ ] **Step 4: Type-check + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src/app/\(customer\)/\[locale\]/account/preferences frontend/messages
git commit -m "feat(account): add /account/preferences stub"
```

---

### Task 1.5: Support page (stub — FAQ + console-logging form)

**Files:**
- Create: `frontend/src/app/(customer)/[locale]/account/support/page.tsx`
- Create: `frontend/src/app/(customer)/[locale]/account/support/page.module.css`

- [ ] **Step 1: Create `page.module.css`**

```css
.page { display: flex; flex-direction: column; gap: var(--space-6); max-width: var(--container-lg); }
.section { background: var(--color-neutral-0); border: 1px solid var(--color-neutral-100); border-radius: var(--radius-md); padding: var(--space-5); }
.title { font-size: var(--font-xl); font-weight: var(--weight-semibold); color: var(--color-neutral-900); margin-bottom: var(--space-2); }
.subtitle { font-size: var(--font-sm); color: var(--color-neutral-500); margin-bottom: var(--space-4); }
.faqList { display: flex; flex-direction: column; gap: var(--space-3); }
.faqItem { padding: var(--space-3); background: var(--color-neutral-50); border-radius: var(--radius-sm); }
.faqQuestion { font-weight: var(--weight-medium); color: var(--color-neutral-900); }
.faqAnswer { font-size: var(--font-sm); color: var(--color-neutral-700); margin-top: var(--space-1); }
.form { display: flex; flex-direction: column; gap: var(--space-4); }
.field { display: flex; flex-direction: column; gap: var(--space-1); }
.label { font-size: var(--font-sm); font-weight: var(--weight-medium); }
.input, .textarea { padding: var(--space-2); border: 1px solid var(--color-neutral-200); border-radius: var(--radius-sm); font: inherit; }
.textarea { min-height: 120px; resize: vertical; }
.toast { padding: var(--space-3); background: var(--color-success-50); border-radius: var(--radius-sm); color: var(--color-success-700); }
```

- [ ] **Step 2: Create `page.tsx`**

```tsx
"use client";
import { useState } from "react";
import { useTranslations } from "next-intl";
import styles from "./page.module.css";

const FAQ_KEYS = ["q1", "q2", "q3", "q4", "q5"] as const;

export default function SupportPage() {
  const t = useTranslations("Account.support");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    // Phase 1 stub — Phase 3 wires this to POST /api/v1/customers/me/support.
    console.log("[support] would send", { subject, message });
    setSent(true);
    setSubject("");
    setMessage("");
  };

  return (
    <div className={styles.page}>
      <section className={styles.section}>
        <h2 className={styles.title}>{t("faqTitle")}</h2>
        <p className={styles.subtitle}>{t("faqSubtitle")}</p>
        <div className={styles.faqList}>
          {FAQ_KEYS.map((k) => (
            <div key={k} className={styles.faqItem}>
              <div className={styles.faqQuestion}>{t(`faq.${k}.question`)}</div>
              <div className={styles.faqAnswer}>{t(`faq.${k}.answer`)}</div>
            </div>
          ))}
        </div>
      </section>
      <section className={styles.section}>
        <h2 className={styles.title}>{t("contactTitle")}</h2>
        <p className={styles.subtitle}>{t("contactSubtitle")}</p>
        <form className={styles.form} onSubmit={submit}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="subject">{t("subjectLabel")}</label>
            <input id="subject" className={styles.input} value={subject} onChange={(e) => setSubject(e.target.value)} required maxLength={120} />
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="message">{t("messageLabel")}</label>
            <textarea id="message" className={styles.textarea} value={message} onChange={(e) => setMessage(e.target.value)} required maxLength={2000} />
          </div>
          <button className="btn btn-primary" type="submit">{t("send")}</button>
          {sent && <div className={styles.toast}>{t("sent")}</div>}
        </form>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Add `Account.support.*` keys**

Add to all five message files under `Account`:

```json
"support": {
  "faqTitle": "Frequently asked questions",
  "faqSubtitle": "Quick answers to common questions.",
  "faq": {
    "q1": { "question": "How do I track my order?", "answer": "Open the order from /account/orders to see its current status and timeline." },
    "q2": { "question": "How do I change my delivery address?", "answer": "Manage saved addresses from /account/addresses; pick one at checkout." },
    "q3": { "question": "What payment methods are supported?", "answer": "UPI and Cash on Delivery." },
    "q4": { "question": "How do I cancel an order?", "answer": "Pending orders can be cancelled from the order detail page." },
    "q5": { "question": "Why didn't I receive my OTP?", "answer": "Check your spam folder or wait 60 seconds and request a new code." }
  },
  "contactTitle": "Contact support",
  "contactSubtitle": "Send us a message and we'll get back to you over email.",
  "subjectLabel": "Subject",
  "messageLabel": "Message",
  "send": "Send",
  "sent": "Message sent. We'll be in touch.",
  "sendError": "Could not send your message. Please try again."
}
```

- [ ] **Step 4: Type-check + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src/app/\(customer\)/\[locale\]/account/support frontend/messages
git commit -m "feat(account): add /account/support stub (FAQ + contact form)"
```

---

### Task 1.6: Retire `/account/settings` (redirect old route)

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/account/settings/page.tsx` → replace with redirect
- Modify: `frontend/src/app/(customer)/[locale]/account/layout.tsx` → drop the settings-specific title branch
- Delete: `frontend/src/app/(customer)/[locale]/account/settings/page.module.css` (no longer referenced)

- [ ] **Step 1: Replace `settings/page.tsx` with a server-side redirect**

```tsx
import { redirect } from "next/navigation";

export default function SettingsRedirect() {
  redirect("/account/profile");
}
```

- [ ] **Step 2: Delete the stale module CSS**

```bash
git rm frontend/src/app/\(customer\)/\[locale\]/account/settings/page.module.css
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```
Expected: clean. If lint flags unused exports anywhere, address by removing references.

- [ ] **Step 4: Manual smoke**

`http://localhost:3000/en/account/settings` → must redirect to `/en/account/profile`. Existing in-app `<Link href="/account/settings">` references survive transparently.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(customer\)/\[locale\]/account/settings
git commit -m "feat(account): retire /account/settings (redirect to /account/profile)"
```

---

### Task 1.7: Open Phase 1 PR

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/customer-dashboard-redesign
```

- [ ] **Step 2: Open the PR via `gh`**

```bash
gh pr create --title "feat(account): customer dashboard shell — split into 6 sections" --body "$(cat <<'EOF'
## Summary
- Replace 2-item customer dashboard nav with 6 sections: Dashboard, Orders, Addresses, Profile, Preferences, Support.
- Split the existing `/account/settings` page into `/account/profile` (identity) and `/account/addresses` (address book) — no functional change.
- Add `/account/preferences` and `/account/support` as stubs (real backend wiring lands in Phase 3).
- Old `/account/settings` redirects to `/account/profile`.

Spec: docs/superpowers/specs/2026-05-14-customer-dashboard-redesign-design.md (Part 1).

## Test plan
- [ ] Lint + type-check pass (`npm run lint`, `tsc --noEmit`).
- [ ] All six sidebar links navigate correctly and highlight active route.
- [ ] `/account/settings` redirects to `/account/profile`.
- [ ] Identity form on `/account/profile` saves successfully.
- [ ] Address CRUD on `/account/addresses` still works (add, edit, set-default, delete).
- [ ] Preferences page renders LocaleSwitcher and a "coming soon" note.
- [ ] Support page renders FAQ + form; submit shows a toast (form is a stub in Phase 1).
EOF
)"
```

- [ ] **Step 3: Wait for explicit user approval to merge.** Do not auto-merge.

Once approved by the user:

```bash
gh pr merge <PR_NUMBER> --merge
```

(No `--delete-branch` — branch retained per project workflow.)

---

## Part 2 — Orders table + dashboard widgets

> Continues on the same `feat/customer-dashboard-redesign` branch after Part 1 merges, or in a follow-up PR off `main`.

### Task 2.1: Customer-stats service (TDD)

**Files:**
- Create: `backend/app/src/app/services/customer_stats.py`
- Create: `backend/app/tests/test_customer_stats.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_customer_stats.py
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.core.security import get_current_customer
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.commerce import (
    Delivery,
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.profile import CustomerProfile
from app.models.store import Store
from app.models.catalog import Service

pytestmark = pytest.mark.asyncio


async def _seed_customer(session, email="c@example.com") -> tuple[User, CustomerProfile]:
    user = User(email=email, role=UserRole.Customer, is_active=True)
    session.add(user)
    await session.flush()
    profile = CustomerProfile(user_id=user.id, first_name="Test")
    session.add(profile)
    await session.flush()
    return user, profile


async def _seed_order(
    session,
    *,
    profile: CustomerProfile,
    store: Store,
    service: Service,
    total: float,
    placed_at: datetime,
    status: OrderStatus = OrderStatus.Delivered,
) -> Order:
    address = Address(
        address_line1="1 Test St", city="X", state="MH", pincode="400001", country="IN"
    )
    session.add(address)
    await session.flush()
    order = Order(
        customer_profile_id=profile.id,
        store_id=store.id,
        service_id=service.id,
        service_name_snapshot=service.slug,
        delivery_address_id=address.id,
        status=status,
        subtotal=total,
        delivery_fee=0,
        tax=0,
        total=total,
        delivery_address_snapshot="1 Test St",
        placed_at=placed_at,
    )
    session.add(order)
    await session.commit()
    return order


async def test_stats_empty(client: AsyncClient, db_session, app):
    user, _profile = await _seed_customer(db_session)
    app.dependency_overrides[get_current_customer] = lambda: user
    try:
        r = await client.get("/api/v1/customers/me/stats")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["orders_this_month"] == 0
    assert data["lifetime_spend"] == 0
    assert data["favorite_store_id"] is None
    assert data["recent_delivered"] == []


async def test_stats_aggregates(client: AsyncClient, db_session, app, store_factory, service_factory):
    user, profile = await _seed_customer(db_session)
    service = await service_factory(db_session)
    store_a = await store_factory(db_session, name="Store A", service=service)
    store_b = await store_factory(db_session, name="Store B", service=service)

    now = datetime.now(timezone.utc)
    # store_a: 3 delivered orders this month, total 1500
    for i in range(3):
        await _seed_order(db_session, profile=profile, store=store_a, service=service,
                          total=500, placed_at=now - timedelta(days=i))
    # store_b: 1 delivered order this month, total 200
    await _seed_order(db_session, profile=profile, store=store_b, service=service,
                      total=200, placed_at=now - timedelta(days=2))
    # store_b: 1 delivered order 2 months ago, total 100
    await _seed_order(db_session, profile=profile, store=store_b, service=service,
                      total=100, placed_at=now - timedelta(days=70))

    app.dependency_overrides[get_current_customer] = lambda: user
    try:
        r = await client.get("/api/v1/customers/me/stats")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["orders_this_month"] == 4
    assert data["lifetime_spend"] == 1800
    assert data["favorite_store_id"] == store_a.id
    assert data["favorite_store_name"] == "Store A"
    assert len(data["recent_delivered"]) == 3
    # Newest first
    assert data["recent_delivered"][0]["total"] == 500
```

The `store_factory` / `service_factory` fixtures are not yet defined — add them to `backend/app/tests/conftest.py` in a sibling step before running this test (see Step 1b below).

- [ ] **Step 1b: Add the missing factories to `conftest.py`**

If `store_factory` and `service_factory` are not already present in `backend/app/tests/conftest.py`, add them:

```python
import pytest
from app.models.catalog import Service
from app.models.store import Store
from app.models.address import Address

@pytest.fixture
async def service_factory():
    async def make(session, *, slug: str = "grocery") -> Service:
        svc = Service(slug=slug, sort_order=1, is_active=True)
        session.add(svc)
        await session.flush()
        return svc
    return make

@pytest.fixture
async def store_factory():
    async def make(session, *, name: str, service: Service) -> Store:
        addr = Address(
            address_line1="1 Store Ln", city="X", state="MH",
            pincode="400001", country="IN",
        )
        session.add(addr)
        await session.flush()
        # Seller user is needed for FK satisfaction; create a throwaway one.
        from app.models.base import User, UserRole
        seller = User(email=f"seller-{name}@example.com", role=UserRole.Seller, is_active=True)
        session.add(seller)
        await session.flush()
        store = Store(
            name=name,
            address_id=addr.id,
            seller_id=seller.id,
            is_active=True,
            delivery_radius_km=5,
            pin_confirmed=True,
        )
        session.add(store)
        await session.flush()
        store.services.append(service)
        await session.commit()
        return store
    return make
```

Inspect `backend/app/src/app/models/store.py` first if these fields don't match — adjust to the real model column names. If equivalent fixtures already exist, skip this step.

- [ ] **Step 2: Run the test — expect failure (endpoint does not exist)**

```bash
cd backend/app && uv run pytest tests/test_customer_stats.py -v
```
Expected: 404 on the `/customers/me/stats` call. Both tests fail.

- [ ] **Step 3: Implement the service**

`backend/app/src/app/services/customer_stats.py`:

```python
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from datetime import datetime, timezone

from sqlalchemy import func, desc, select as sa_select
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Order, OrderStatus
from app.models.store import Store
from app.schemas.customer_stats import CustomerStatsResponse, OrderSummary


def _start_of_month_utc(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def compute_stats(session: AsyncSession, customer_profile_id: int) -> CustomerStatsResponse:
    now = datetime.now(timezone.utc)
    month_start = _start_of_month_utc(now)

    orders_this_month_q = (
        sa_select(func.count(Order.id))
        .where(Order.customer_profile_id == customer_profile_id)
        .where(Order.placed_at >= month_start)
    )
    orders_this_month = (await session.execute(orders_this_month_q)).scalar() or 0

    lifetime_spend_q = (
        sa_select(func.coalesce(func.sum(Order.total), 0))
        .where(Order.customer_profile_id == customer_profile_id)
        .where(Order.status == OrderStatus.Delivered)
    )
    lifetime_spend = float((await session.execute(lifetime_spend_q)).scalar() or 0)

    fav_q = (
        sa_select(Order.store_id, func.count(Order.id).label("c"), func.max(Order.placed_at).label("recent"))
        .where(Order.customer_profile_id == customer_profile_id)
        .where(Order.status == OrderStatus.Delivered)
        .group_by(Order.store_id)
        .order_by(desc("c"), desc("recent"))
        .limit(1)
    )
    fav_row = (await session.execute(fav_q)).first()
    favorite_store_id = fav_row[0] if fav_row else None
    favorite_store_name: str | None = None
    if favorite_store_id is not None:
        favorite_store_name = (
            await session.exec(select(Store.name).where(Store.id == favorite_store_id))
        ).first()

    recent_q = (
        select(Order)
        .where(Order.customer_profile_id == customer_profile_id)
        .where(Order.status == OrderStatus.Delivered)
        .order_by(desc(Order.placed_at))
        .limit(3)
    )
    recent_orders = list((await session.exec(recent_q)).all())

    store_ids = {o.store_id for o in recent_orders} | {favorite_store_id} if recent_orders else set()
    store_ids.discard(None)
    name_by_store: dict[int, str] = {}
    if store_ids:
        rows = (await session.exec(select(Store.id, Store.name).where(Store.id.in_(store_ids)))).all()
        for sid, nm in rows:
            name_by_store[sid] = nm
    if favorite_store_id is not None and favorite_store_name is None:
        favorite_store_name = name_by_store.get(favorite_store_id)

    return CustomerStatsResponse(
        orders_this_month=orders_this_month,
        lifetime_spend=lifetime_spend,
        favorite_store_id=favorite_store_id,
        favorite_store_name=favorite_store_name,
        recent_delivered=[
            OrderSummary(
                id=o.id,
                store_id=o.store_id,
                store_name=name_by_store.get(o.store_id, ""),
                service_id=o.service_id,
                service_name=o.service_name_snapshot,
                total=o.total,
                placed_at=o.placed_at,
            )
            for o in recent_orders
        ],
    )
```

`backend/app/src/app/schemas/customer_stats.py`:

```python
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from datetime import datetime

from pydantic import BaseModel


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
    recent_delivered: list[OrderSummary]
```

- [ ] **Step 4: Add the route**

In `backend/app/src/app/api/customers.py`, append:

```python
from app.schemas.customer_stats import CustomerStatsResponse
from app.services.customer_stats import compute_stats


@router.get("/me/stats", response_model=CustomerStatsResponse)
async def customer_stats(
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerStatsResponse:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    assert profile.id is not None
    return await compute_stats(session, profile.id)
```

- [ ] **Step 5: Run tests — expect pass**

```bash
cd backend/app && uv run pytest tests/test_customer_stats.py -v
```
Expected: both tests pass.

- [ ] **Step 6: Lint + type-check**

```bash
cd backend/app && uv run ruff check . && uv run mypy .
```
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add backend/app/src/app/services/customer_stats.py backend/app/src/app/schemas/customer_stats.py backend/app/src/app/api/customers.py backend/app/tests/test_customer_stats.py backend/app/tests/conftest.py
git commit -m "feat(customers): add /customers/me/stats aggregate endpoint"
```

---

### Task 2.2: Frontend stats fetcher + types

**Files:**
- Modify: `frontend/src/lib/orders.ts` (add `getCustomerStats`)
- Modify: `frontend/src/types/index.ts` (add `CustomerStats` + `OrderSummary`)

- [ ] **Step 1: Extend `types/index.ts`**

Append to `frontend/src/types/index.ts`:

```ts
export interface CustomerOrderSummary {
  id: number;
  store_id: number;
  store_name: string;
  service_id: number;
  service_name: string;
  total: number;
  placed_at: string;
}

export interface CustomerStats {
  orders_this_month: number;
  lifetime_spend: number;
  favorite_store_id: number | null;
  favorite_store_name: string | null;
  recent_delivered: CustomerOrderSummary[];
}
```

- [ ] **Step 2: Add fetcher**

Append to `frontend/src/lib/orders.ts`:

```ts
import type { CustomerStats } from "@/types";

export async function getCustomerStats(token: string): Promise<CustomerStats> {
  return get<CustomerStats>("/api/v1/customers/me/stats", token);
}
```

- [ ] **Step 3: Type-check + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src/lib/orders.ts frontend/src/types/index.ts
git commit -m "feat(orders): add getCustomerStats fetcher and types"
```

---

### Task 2.3: PaymentStatusPill component

**Files:**
- Create: `frontend/src/components/orders/PaymentStatusPill.tsx`
- Create: `frontend/src/components/orders/PaymentStatusPill.module.css`

- [ ] **Step 1: Create component**

```tsx
"use client";
import { useTranslations } from "next-intl";
import type { OrderPayment } from "@/types";
import styles from "./PaymentStatusPill.module.css";

const STATUS_CLASS: Record<string, string> = {
  pending: styles.pending,
  paid: styles.paid,
  failed: styles.failed,
  refunded: styles.refunded,
};

export default function PaymentStatusPill({ payment }: { payment: OrderPayment }) {
  const t = useTranslations("Order.payment");
  return (
    <span className={`${styles.pill} ${STATUS_CLASS[payment.status] ?? ""}`}>
      <span className={styles.method}>{payment.method.toUpperCase()}</span>
      <span className={styles.dot}>·</span>
      <span className={styles.status}>{t(`status.${payment.status}`)}</span>
    </span>
  );
}
```

- [ ] **Step 2: Create CSS**

```css
.pill { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; font-size: var(--font-xs); font-weight: var(--weight-medium); border: 1px solid transparent; }
.method { font-family: var(--font-mono, monospace); }
.dot { opacity: 0.6; }
.status { text-transform: capitalize; }
.pending { background: var(--color-warning-50); color: var(--color-warning-700); border-color: var(--color-warning-200); }
.paid { background: var(--color-success-50); color: var(--color-success-700); border-color: var(--color-success-200); }
.failed { background: var(--color-danger-50); color: var(--color-danger-700); border-color: var(--color-danger-200); }
.refunded { background: var(--color-neutral-100); color: var(--color-neutral-700); border-color: var(--color-neutral-200); }
```

Substitute the actual semantic-color token names if these don't exist in `design-tokens.css`. Grep the file first:
```bash
grep -E 'success|warning|danger' frontend/src/styles/design-tokens.css | head
```

- [ ] **Step 3: Add `Order.payment.status.*` keys**

Add to `frontend/messages/{en,hi,mr,gu,pa}.json` under `Order`:

```json
"payment": {
  "status": {
    "pending": "Pending",
    "paid": "Paid",
    "failed": "Failed",
    "refunded": "Refunded"
  }
}
```

If `Order.payment` already exists, merge into it.

- [ ] **Step 4: Type-check + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src/components/orders/PaymentStatusPill.tsx frontend/src/components/orders/PaymentStatusPill.module.css frontend/messages
git commit -m "feat(orders): add PaymentStatusPill component"
```

---

### Task 2.4: Rewrite `/account/orders` to a DataTable

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/account/orders/page.tsx`
- Modify: `frontend/src/app/(customer)/[locale]/account/orders/page.module.css` (add filter-strip styles)

- [ ] **Step 1: Rewrite `page.tsx`**

Replace its current body. Key behaviors: status chips (All/Active/Delivered/Cancelled), service dropdown sourced from `GET /api/v1/catalog/services`, optional date-range inputs, search input filtering by `#${id}` or `store_name`, sortable Date/Total cols, "Load more" pagination at 20 rows.

```tsx
"use client";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useSearchParams, useRouter } from "next/navigation";
import DataTable, { type Column } from "@/components/DataTable";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import PaymentStatusPill from "@/components/orders/PaymentStatusPill";
import { listOrders } from "@/lib/orders";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import type { Order, OrderStatus, Service } from "@/types";
import styles from "./page.module.css";

const ACTIVE: OrderStatus[] = ["pending", "packed", "dispatched"];
type StatusFilter = "all" | "active" | "delivered" | "cancelled";
type SortKey = "date_desc" | "date_asc" | "total_desc" | "total_asc";
const PAGE_SIZE = 20;

export default function CustomerOrdersPage() {
  const { token } = useAuth();
  const t = useTranslations("Account.orders");
  const router = useRouter();
  const search = useSearchParams();
  const justPlaced = search.get("placed");

  const [allOrders, setAllOrders] = useState<Order[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [serviceId, setServiceId] = useState<string>("");
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [query, setQuery] = useState<string>("");
  const [sortKey, setSortKey] = useState<SortKey>("date_desc");
  const [pageCount, setPageCount] = useState(1);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    Promise.all([
      listOrders(token),
      get<Service[]>("/api/v1/catalog/services"),
    ])
      .then(([orders, svcs]) => {
        if (cancelled) return;
        setAllOrders(orders);
        setServices(svcs);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [token]);

  const filtered = useMemo(() => {
    let out = allOrders.slice();
    if (statusFilter === "active") out = out.filter((o) => ACTIVE.includes(o.status));
    else if (statusFilter === "delivered") out = out.filter((o) => o.status === "delivered");
    else if (statusFilter === "cancelled") out = out.filter((o) => o.status === "cancelled");
    if (serviceId) out = out.filter((o) => String(o.service_id) === serviceId);
    if (fromDate) out = out.filter((o) => o.placed_at >= fromDate);
    if (toDate) out = out.filter((o) => o.placed_at <= `${toDate}T23:59:59Z`);
    if (query.trim()) {
      const q = query.trim().toLowerCase().replace(/^#/, "");
      out = out.filter((o) =>
        String(o.id).includes(q) || o.store_name.toLowerCase().includes(q),
      );
    }
    out.sort((a, b) => {
      switch (sortKey) {
        case "date_asc": return a.placed_at.localeCompare(b.placed_at);
        case "total_asc": return a.total - b.total;
        case "total_desc": return b.total - a.total;
        case "date_desc":
        default: return b.placed_at.localeCompare(a.placed_at);
      }
    });
    return out;
  }, [allOrders, statusFilter, serviceId, fromDate, toDate, query, sortKey]);

  const visible = filtered.slice(0, pageCount * PAGE_SIZE);

  const columns: Column<Order>[] = [
    { key: "id", label: t("colOrderId"), render: (o) => <span className={styles.mono}>#{o.id}</span> },
    { key: "placed_at", label: t("colDate"), render: (o) => <time title={o.placed_at}>{new Date(o.placed_at).toLocaleString()}</time> },
    { key: "store_name", label: t("colStore") },
    { key: "service_name", label: t("colService"), render: (o) => <span className={styles.chip}>{o.service_name}</span> },
    { key: "items", label: t("colItems"), render: (o) => t("itemCount", { count: o.items.length }) },
    { key: "total", label: t("colTotal"), render: (o) => <span className={styles.right}>₹{o.total.toFixed(2)}</span> },
    { key: "payment", label: t("colPayment"), render: (o) => <PaymentStatusPill payment={o.payment} /> },
    { key: "status", label: t("colStatus"), render: (o) => <OrderStatusBadge status={o.status} /> },
  ];

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{t("title")}</h1>
      {justPlaced && (
        <div className={styles.toast}>{t("placedToast", { count: Number(justPlaced) })}</div>
      )}

      <div className={styles.controls}>
        <div className={styles.chips} role="tablist">
          {(["all", "active", "delivered", "cancelled"] as StatusFilter[]).map((s) => (
            <button key={s}
              className={statusFilter === s ? styles.chipActive : styles.chip}
              onClick={() => { setStatusFilter(s); setPageCount(1); }}
            >{t(`chip.${s}`)}</button>
          ))}
        </div>
        <select className={styles.select} value={serviceId} onChange={(e) => { setServiceId(e.target.value); setPageCount(1); }}>
          <option value="">{t("allServices")}</option>
          {services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <input type="date" className={styles.dateInput} value={fromDate} onChange={(e) => setFromDate(e.target.value)} aria-label={t("fromDate")} />
        <input type="date" className={styles.dateInput} value={toDate} onChange={(e) => setToDate(e.target.value)} aria-label={t("toDate")} />
        <input type="search" className={styles.search} placeholder={t("searchPlaceholder")} value={query} onChange={(e) => { setQuery(e.target.value); setPageCount(1); }} />
        <select className={styles.select} value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}>
          <option value="date_desc">{t("sort.dateDesc")}</option>
          <option value="date_asc">{t("sort.dateAsc")}</option>
          <option value="total_desc">{t("sort.totalDesc")}</option>
          <option value="total_asc">{t("sort.totalAsc")}</option>
        </select>
      </div>

      {loading ? (
        <div className={styles.empty}>{t("loading")}</div>
      ) : (
        <>
          <div onClick={(e) => {
            const tr = (e.target as HTMLElement).closest("tr[data-order-id]");
            if (tr) router.push(`/account/orders/${tr.getAttribute("data-order-id")}`);
          }}>
            <DataTable
              columns={columns}
              data={visible}
              keyField="id"
              emptyMessage={t("emptyHistory")}
              mobileCardRender={(o) => (
                <a href={`/account/orders/${o.id}`} className={styles.mobileLink}>
                  <div className={styles.mobileTop}>
                    <span className={styles.mono}>#{o.id}</span>
                    <OrderStatusBadge status={o.status} />
                  </div>
                  <div>{o.store_name} · {o.service_name}</div>
                  <div className={styles.mobileBot}>
                    <span>₹{o.total.toFixed(2)}</span>
                    <PaymentStatusPill payment={o.payment} />
                  </div>
                </a>
              )}
            />
          </div>
          {visible.length < filtered.length && (
            <button className="btn btn-outline" onClick={() => setPageCount((p) => p + 1)}>
              {t("loadMore")}
            </button>
          )}
        </>
      )}
    </div>
  );
}
```

> Row-click navigation: the wrapper `<div onClick>` reads `data-order-id` from the row. `DataTable` does not currently set that attribute; modify it in Step 2.

- [ ] **Step 2: Patch `DataTable.tsx` to expose `data-order-id`**

In `frontend/src/components/DataTable.tsx`, modify the `<tr>` inside the body loop to include `data-order-id={String(rec[keyField])}`. One-line addition; do not change other behavior.

- [ ] **Step 3: Add filter-strip + table-tweak CSS**

Append to `frontend/src/app/(customer)/[locale]/account/orders/page.module.css`:

```css
.controls { display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: center; margin-bottom: var(--space-4); }
.chips { display: inline-flex; gap: var(--space-1); }
.chip, .chipActive { padding: 4px 12px; border-radius: 999px; border: 1px solid var(--color-neutral-200); background: var(--color-neutral-0); font-size: var(--font-sm); cursor: pointer; }
.chipActive { background: var(--color-primary-50); border-color: var(--color-primary-300); color: var(--color-primary-700); font-weight: var(--weight-medium); }
.select, .dateInput, .search { padding: 6px 10px; border: 1px solid var(--color-neutral-200); border-radius: var(--radius-sm); font: inherit; }
.search { min-width: 220px; }
.mono { font-family: var(--font-mono, monospace); }
.right { text-align: right; display: block; }
.mobileLink { display: flex; flex-direction: column; gap: 6px; color: inherit; text-decoration: none; }
.mobileTop, .mobileBot { display: flex; justify-content: space-between; align-items: center; }
```

If `--color-primary-*` tokens don't exist, substitute the project's actual primary color tokens (grep `design-tokens.css`).

- [ ] **Step 4: Add orders-table translation keys**

Add to each `Account.orders` block in `frontend/messages/{en,hi,mr,gu,pa}.json`:

```json
"colOrderId": "Order #",
"colDate": "Date",
"colStore": "Store",
"colService": "Service",
"colItems": "Items",
"colTotal": "Total",
"colPayment": "Payment",
"colStatus": "Status",
"itemCount": "{count, plural, one {# item} other {# items}}",
"allServices": "All services",
"fromDate": "From date",
"toDate": "To date",
"searchPlaceholder": "Search by order # or store…",
"loadMore": "Load more",
"chip": {
  "all": "All",
  "active": "Active",
  "delivered": "Delivered",
  "cancelled": "Cancelled"
},
"sort": {
  "dateDesc": "Newest first",
  "dateAsc": "Oldest first",
  "totalDesc": "Total ↓",
  "totalAsc": "Total ↑"
}
```

- [ ] **Step 5: Type-check + manual smoke**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```
Run `./scripts/dev.sh start`. Place a few test orders. On `/account/orders`: chips toggle filter, service dropdown filters, date range filters, search filters, sort changes order, row click navigates to detail, mobile (< 720px) shows card list.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/\(customer\)/\[locale\]/account/orders frontend/src/components/DataTable.tsx frontend/messages
git commit -m "feat(account): rewrite /account/orders as filterable DataTable"
```

---

### Task 2.5: Dashboard landing widgets

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/account/page.tsx`
- Create: `frontend/src/app/(customer)/[locale]/account/page.module.css`

- [ ] **Step 1: Create the dashboard module CSS**

```css
.page { display: grid; grid-template-columns: 1fr; gap: var(--space-6); max-width: var(--container-lg); }
@media (min-width: 720px) { .page { grid-template-columns: 1fr 1fr; } .full { grid-column: 1 / -1; } }
.greet { background: var(--color-neutral-0); border: 1px solid var(--color-neutral-100); border-radius: var(--radius-md); padding: var(--space-5); }
.greetTitle { font-size: var(--font-xl); font-weight: var(--weight-semibold); margin: 0; }
.greetSub { color: var(--color-neutral-500); font-size: var(--font-sm); margin-top: 4px; }
.statsStrip { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-3); }
.rail { display: flex; flex-direction: column; gap: var(--space-3); }
.railTitle { font-size: var(--font-lg); font-weight: var(--weight-semibold); margin: 0; }
.railList { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--space-3); }
.railCard { background: var(--color-neutral-0); border: 1px solid var(--color-neutral-100); border-radius: var(--radius-md); padding: var(--space-3); text-decoration: none; color: inherit; display: flex; flex-direction: column; gap: 4px; }
.railStore { font-weight: var(--weight-medium); }
.railMeta { font-size: var(--font-sm); color: var(--color-neutral-500); }
```

- [ ] **Step 2: Rewrite `page.tsx`**

```tsx
"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import ActiveOrdersWidget from "@/components/orders/ActiveOrdersWidget";
import StatsCard from "@/components/StatsCard";
import { getCustomerStats } from "@/lib/orders";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import type { CustomerStats, CustomerProfile } from "@/types";
import styles from "./page.module.css";

export default function AccountHomePage() {
  const t = useTranslations("Account.dashboard");
  const { token } = useAuth();
  const [stats, setStats] = useState<CustomerStats | null>(null);
  const [firstName, setFirstName] = useState<string>("");

  useEffect(() => {
    if (!token) return;
    getCustomerStats(token).then(setStats).catch(() => setStats(null));
    get<CustomerProfile>("/api/v1/customers/me", token)
      .then((p) => setFirstName(p.first_name))
      .catch(() => {});
  }, [token]);

  const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className={styles.page}>
      <section className={`${styles.greet} ${styles.full}`}>
        <h1 className={styles.greetTitle}>{t("greeting", { name: firstName || t("there") })} 👋</h1>
        <p className={styles.greetSub}>{today}</p>
      </section>

      <section className={styles.full}>
        <ActiveOrdersWidget role="customer" limit={5} />
      </section>

      {stats && (
        <section className={`${styles.statsStrip} ${styles.full}`}>
          <StatsCard label={t("ordersThisMonth")} value={String(stats.orders_this_month)} />
          <StatsCard label={t("lifetimeSpend")} value={`₹${stats.lifetime_spend.toFixed(0)}`} />
          <StatsCard label={t("favoriteStore")} value={stats.favorite_store_name ?? "—"} />
        </section>
      )}

      {stats && stats.recent_delivered.length > 0 && (
        <section className={`${styles.rail} ${styles.full}`}>
          <h2 className={styles.railTitle}>{t("orderAgain")}</h2>
          <div className={styles.railList}>
            {stats.recent_delivered.map((o) => (
              <Link key={o.id} href={`/account/orders/${o.id}`} className={styles.railCard}>
                <span className={styles.railStore}>{o.store_name}</span>
                <span className={styles.railMeta}>{o.service_name} · ₹{o.total.toFixed(0)}</span>
                <span className={styles.railMeta}>{new Date(o.placed_at).toLocaleDateString()}</span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
```

If `StatsCard` does not accept `{ label, value }` props, check `frontend/src/components/StatsCard.tsx` and adapt — keep the same render but use the real props.

- [ ] **Step 3: Add `Account.dashboard.*` keys**

```json
"dashboard": {
  "greeting": "Hi, {name}",
  "there": "there",
  "ordersThisMonth": "Orders this month",
  "lifetimeSpend": "Lifetime spend",
  "favoriteStore": "Favorite store",
  "orderAgain": "Order again"
}
```

Replicate in all five message files.

- [ ] **Step 4: Type-check + smoke + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src/app/\(customer\)/\[locale\]/account/page.tsx frontend/src/app/\(customer\)/\[locale\]/account/page.module.css frontend/messages
git commit -m "feat(account): rebuild dashboard landing with stats and order-again rail"
```

---

### Task 2.6: Open Phase 2 PR

- [ ] **Step 1: Push + open PR**

```bash
git push
gh pr create --title "feat(account): orders table + dashboard widgets" --body "$(cat <<'EOF'
## Summary
- New `GET /api/v1/customers/me/stats` aggregate endpoint (orders this month, lifetime spend, favorite store, last 3 delivered).
- `/account/orders` rebuilt as a sortable, filterable DataTable with status chips, service dropdown, date range, search.
- `/account` landing: greeting + active orders + stats strip + order-again rail.

Spec: docs/superpowers/specs/2026-05-14-customer-dashboard-redesign-design.md (Part 2).

## Test plan
- [ ] Backend tests pass (`uv run pytest tests/test_customer_stats.py -v`).
- [ ] Lint, mypy, ruff clean (backend); npm lint + tsc clean (frontend).
- [ ] Orders table: chips/service/date/search/sort all work; row click → detail; mobile renders as cards.
- [ ] Dashboard: greeting shows first name; stats card values match seeded orders; order-again rail links to detail.
- [ ] Empty-state customer (no orders) renders without errors.
EOF
)"
```

- [ ] **Step 2: Wait for user approval, then merge with `gh pr merge <N> --merge`.**

---

## Part 3 — Profile + Preferences + extras

### Task 3.1: Backend — Alembic migration for customerprofile + review constraints

**Files:**
- Create: `backend/app/migrations/versions/<auto>_customer_dashboard_redesign.py` (generated)

- [ ] **Step 1: Add new columns to `CustomerProfile`** in `backend/app/src/app/models/profile.py`

Inside the existing `CustomerProfile` class (before the `user` Relationship):

```python
preferred_language: Optional[str] = Field(default=None, max_length=8)
marketing_opt_in: bool = Field(default=False, nullable=False)
notify_order_email: bool = Field(default=True, nullable=False)
notify_order_sms: bool = Field(default=False, nullable=False)
phone_verified_at: Optional[datetime] = Field(  # type: ignore[call-overload]
    default=None,
    sa_type=DateTime(timezone=True),
)
```

Add the needed imports at the top of the file:

```python
from datetime import datetime
from sqlalchemy import DateTime
```

Do not touch the already-defined `date_of_birth` / `gender` columns.

- [ ] **Step 2: Generate the Alembic migration**

```bash
cd backend/app && uv run alembic revision --autogenerate -m "customer dashboard redesign — profile prefs + phone verification + review constraints"
```

Open the generated file. The autogen should pick up the five new columns on `customerprofile`. Manually add the partial unique index and CHECK constraint on the existing `review` table (autogen will not infer them):

```python
op.create_index(
    "uq_review_order_id",
    "review",
    ["order_id"],
    unique=True,
    postgresql_where=sa.text("order_id IS NOT NULL"),
)
op.create_check_constraint(
    "ck_review_rating_range",
    "review",
    "rating BETWEEN 1 AND 5",
)
```

Mirror these in the `downgrade()` function:

```python
op.drop_constraint("ck_review_rating_range", "review", type_="check")
op.drop_index("uq_review_order_id", table_name="review")
```

Inspect the upgrade body for any unexpected drops/adds against PostGIS tables or `geo` columns — those are auto-skipped by `migrations/env.py` but always sanity-check.

- [ ] **Step 3: Apply + smoke**

```bash
cd backend/app && uv run alembic upgrade head
```
Expected: clean upgrade. Then verify the columns exist:

```bash
docker compose exec db psql -U khanabazaar -d khanabazaar -c "\d customerprofile"
docker compose exec db psql -U khanabazaar -d khanabazaar -c "\d review"
```

Roll-back smoke:
```bash
uv run alembic downgrade -1 && uv run alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/models/profile.py backend/app/migrations/versions
git commit -m "feat(db): add customerprofile prefs columns + review constraints"
```

---

### Task 3.2: Backend — Preferences endpoint (TDD)

**Files:**
- Modify: `backend/app/src/app/schemas/customers.py` (extend read schema + new update schema)
- Modify: `backend/app/src/app/api/customers.py` (new PATCH route + extend existing)
- Create: `backend/app/tests/test_customer_preferences.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/app/tests/test_customer_preferences.py
import pytest
from httpx import AsyncClient

from app.core.security import get_current_customer
from app.models.base import User, UserRole
from app.models.profile import CustomerProfile

pytestmark = pytest.mark.asyncio


async def _make_customer(db_session) -> User:
    user = User(email="pref@example.com", role=UserRole.Customer, is_active=True)
    db_session.add(user)
    await db_session.flush()
    db_session.add(CustomerProfile(user_id=user.id, first_name="Pref"))
    await db_session.commit()
    return user


async def test_patch_preferences_updates_fields(client: AsyncClient, db_session, app):
    user = await _make_customer(db_session)
    app.dependency_overrides[get_current_customer] = lambda: user
    try:
        r = await client.patch(
            "/api/v1/customers/me/preferences",
            json={"preferred_language": "hi", "marketing_opt_in": True,
                  "notify_order_email": False, "notify_order_sms": True},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["preferred_language"] == "hi"
    assert data["marketing_opt_in"] is True
    assert data["notify_order_email"] is False
    assert data["notify_order_sms"] is True


async def test_patch_preferences_rejects_unknown_language(client: AsyncClient, db_session, app):
    user = await _make_customer(db_session)
    app.dependency_overrides[get_current_customer] = lambda: user
    try:
        r = await client.patch(
            "/api/v1/customers/me/preferences",
            json={"preferred_language": "fr"},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 422


async def test_patch_preferences_partial(client: AsyncClient, db_session, app):
    user = await _make_customer(db_session)
    # Set initial state.
    app.dependency_overrides[get_current_customer] = lambda: user
    try:
        await client.patch("/api/v1/customers/me/preferences",
                           json={"marketing_opt_in": True})
        r = await client.patch("/api/v1/customers/me/preferences",
                               json={"notify_order_sms": True})
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 200
    data = r.json()
    assert data["marketing_opt_in"] is True  # preserved
    assert data["notify_order_sms"] is True
```

- [ ] **Step 2: Run — expect failure**

```bash
cd backend/app && uv run pytest tests/test_customer_preferences.py -v
```
Expected: 404 (endpoint missing).

- [ ] **Step 3: Extend schemas**

In `backend/app/src/app/schemas/customers.py`, add fields to `CustomerProfileRead`:

```python
date_of_birth: date | None = None
preferred_language: str | None = None
marketing_opt_in: bool = False
notify_order_email: bool = True
notify_order_sms: bool = False
phone_verified_at: datetime | None = None
```

Add a new update schema (use the `LanguageCode` enum for validation — import it from `app.models.catalog`):

```python
class CustomerPreferencesUpdate(BaseModel):
    preferred_language: LanguageCode | None = None
    marketing_opt_in: bool | None = None
    notify_order_email: bool | None = None
    notify_order_sms: bool | None = None
```

Also extend `CustomerProfileUpdate` with `date_of_birth: date | None = None`.

Update `_profile_response` in `api/customers.py` to populate the new read fields on `CustomerProfileRead`.

- [ ] **Step 4: Add the route**

In `backend/app/src/app/api/customers.py`:

```python
from app.schemas.customers import CustomerPreferencesUpdate


@router.patch("/me/preferences", response_model=CustomerProfileRead)
async def update_customer_preferences(
    body: CustomerPreferencesUpdate,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    if "preferred_language" in body.model_fields_set:
        profile.preferred_language = body.preferred_language.value if body.preferred_language else None
    if "marketing_opt_in" in body.model_fields_set:
        profile.marketing_opt_in = bool(body.marketing_opt_in)
    if "notify_order_email" in body.model_fields_set:
        profile.notify_order_email = bool(body.notify_order_email)
    if "notify_order_sms" in body.model_fields_set:
        profile.notify_order_sms = bool(body.notify_order_sms)
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return await _profile_response(session, current_user, profile)
```

- [ ] **Step 5: Run tests — expect pass**

```bash
cd backend/app && uv run pytest tests/test_customer_preferences.py -v
```
All three tests pass.

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check . && uv run mypy .
git add backend/app/src/app/schemas/customers.py backend/app/src/app/api/customers.py backend/app/tests/test_customer_preferences.py
git commit -m "feat(customers): add PATCH /customers/me/preferences"
```

---

### Task 3.3: Backend — Phone OTP verification (TDD)

**Files:**
- Modify: `backend/app/src/app/api/customers.py` (two new routes)
- Create: `backend/app/tests/test_customer_phone_verification.py`

- [ ] **Step 1: Write failing test**

```python
# backend/app/tests/test_customer_phone_verification.py
import pytest
from httpx import AsyncClient

from app.core.security import get_current_customer
from app.models.base import User, UserRole
from app.models.profile import CustomerProfile

pytestmark = pytest.mark.asyncio


async def _make_customer(db_session, email: str = "phone@example.com") -> User:
    user = User(email=email, role=UserRole.Customer, is_active=True)
    db_session.add(user)
    await db_session.flush()
    db_session.add(CustomerProfile(user_id=user.id, first_name="X"))
    await db_session.commit()
    return user


async def test_phone_otp_happy_path(client: AsyncClient, db_session, app, redis_client):
    user = await _make_customer(db_session)
    app.dependency_overrides[get_current_customer] = lambda: user
    try:
        r = await client.post(
            "/api/v1/customers/me/phone/otp/request",
            json={"phone": "+919876543210"},
        )
        assert r.status_code == 200, r.text
        # Pull the OTP from Redis (console SMS provider in tests).
        raw = await redis_client.hgetall("otp:customer_phone:code:+919876543210")
        code = raw[b"code"].decode() if isinstance(raw.get(b"code"), bytes) else raw["code"]
        r = await client.post(
            "/api/v1/customers/me/phone/otp/verify",
            json={"phone": "+919876543210", "code": code},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["phone"] == "+919876543210"
    assert data["phone_verified_at"] is not None


async def test_phone_otp_wrong_code(client: AsyncClient, db_session, app):
    user = await _make_customer(db_session, email="phone2@example.com")
    app.dependency_overrides[get_current_customer] = lambda: user
    try:
        await client.post("/api/v1/customers/me/phone/otp/request",
                          json={"phone": "+919876543211"})
        r = await client.post(
            "/api/v1/customers/me/phone/otp/verify",
            json={"phone": "+919876543211", "code": "000000"},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code in (400, 422)


async def test_phone_already_in_use(client: AsyncClient, db_session, app, redis_client):
    # Seed another customer with the phone already verified.
    existing = await _make_customer(db_session, email="other@example.com")
    profile_q = await db_session.exec(
        __import__("sqlmodel").select(CustomerProfile).where(CustomerProfile.user_id == existing.id)
    )
    other_profile = profile_q.first()
    other_profile.phone = "+919999999999"
    db_session.add(other_profile)
    await db_session.commit()

    user = await _make_customer(db_session, email="me@example.com")
    app.dependency_overrides[get_current_customer] = lambda: user
    try:
        r = await client.post(
            "/api/v1/customers/me/phone/otp/request",
            json={"phone": "+919999999999"},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "phone_already_in_use"
```

The `redis_client` fixture must exist in `conftest.py` — if not, add one returning a fresh `aioredis.Redis` from `core/redis.py`, flushed per-test.

- [ ] **Step 2: Run — expect failure** (`uv run pytest tests/test_customer_phone_verification.py -v`).

- [ ] **Step 3: Add the two routes** in `api/customers.py`

```python
import re
from datetime import datetime, timezone
from fastapi import Body
from sqlalchemy.exc import IntegrityError

from app.core.otp import generate_and_store, verify_and_clear
from app.core.redis import get_redis
from app.core.sms import send_otp_sms

E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


async def _phone_in_use_by_other(session, phone: str, current_profile_id: int) -> bool:
    result = await session.exec(
        select(CustomerProfile).where(
            CustomerProfile.phone == phone,
            CustomerProfile.id != current_profile_id,
        )
    )
    return result.first() is not None


@router.post("/me/phone/otp/request")
async def request_phone_otp(
    body: dict = Body(...),
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
):
    phone = (body.get("phone") or "").strip()
    if not E164_RE.match(phone):
        raise HTTPException(status_code=422, detail={"error": "phone_invalid"})
    profile = await _customer_profile_for_user(session, current_user.id)
    if await _phone_in_use_by_other(session, phone, profile.id):
        raise HTTPException(status_code=409, detail={"error": "phone_already_in_use"})
    redis = await get_redis()
    code = await generate_and_store(phone, redis, namespace="customer_phone")
    await send_otp_sms(phone, code)
    return {"sent": True}


@router.post("/me/phone/otp/verify", response_model=CustomerProfileRead)
async def verify_phone_otp(
    body: dict = Body(...),
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
):
    phone = (body.get("phone") or "").strip()
    code = (body.get("code") or "").strip()
    if not E164_RE.match(phone):
        raise HTTPException(status_code=422, detail={"error": "phone_invalid"})
    profile = await _customer_profile_for_user(session, current_user.id)
    if await _phone_in_use_by_other(session, phone, profile.id):
        raise HTTPException(status_code=409, detail={"error": "phone_already_in_use"})
    redis = await get_redis()
    ok = await verify_and_clear(phone, code, redis, namespace="customer_phone")
    if not ok:
        raise HTTPException(status_code=422, detail={"error": "otp_invalid"})
    profile.phone = phone
    profile.phone_verified_at = datetime.now(timezone.utc)
    session.add(profile)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"error": "phone_already_in_use"})
    await session.refresh(profile)
    return await _profile_response(session, current_user, profile)
```

Adjust the imports of `generate_and_store` and `verify_and_clear` to match the real names in `core/otp.py` (the file's `request_otp` / `verify_otp` helpers — read the file and use the actual symbols).

- [ ] **Step 4: Run tests — expect pass.** Iterate on minor mismatches.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check . && uv run mypy .
git add backend/app/src/app/api/customers.py backend/app/tests/test_customer_phone_verification.py
git commit -m "feat(customers): add phone OTP request/verify routes"
```

---

### Task 3.4: Backend — Order reviews (TDD)

**Files:**
- Create: `backend/app/src/app/schemas/reviews.py`
- Modify: `backend/app/src/app/api/orders.py` (add POST review + extend GET response)
- Modify: `backend/app/src/app/schemas/orders.py` (extend `OrderRead` with `review`)
- Create: `backend/app/tests/test_order_reviews.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/app/tests/test_order_reviews.py
import pytest
from httpx import AsyncClient

from app.core.security import get_current_customer
from app.models.commerce import OrderStatus

pytestmark = pytest.mark.asyncio


async def test_review_happy_path(client, db_session, app, delivered_order_factory):
    user, order = await delivered_order_factory(db_session)
    app.dependency_overrides[get_current_customer] = lambda: user
    try:
        r = await client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 5, "comment": "Great!"},
        )
        assert r.status_code == 200, r.text
        r2 = await client.get(f"/api/v1/orders/{order.id}")
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r2.json()["review"]["rating"] == 5


async def test_review_rejects_not_delivered(client, db_session, app, pending_order_factory):
    user, order = await pending_order_factory(db_session)
    app.dependency_overrides[get_current_customer] = lambda: user
    try:
        r = await client.post(f"/api/v1/orders/{order.id}/review", json={"rating": 5})
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "order_not_delivered"


async def test_review_rejects_duplicate(client, db_session, app, delivered_order_factory):
    user, order = await delivered_order_factory(db_session)
    app.dependency_overrides[get_current_customer] = lambda: user
    try:
        await client.post(f"/api/v1/orders/{order.id}/review", json={"rating": 5})
        r = await client.post(f"/api/v1/orders/{order.id}/review", json={"rating": 4})
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "review_exists"


async def test_review_rejects_non_owner(client, db_session, app, delivered_order_factory, customer_factory):
    _owner, order = await delivered_order_factory(db_session)
    other = await customer_factory(db_session, email="other@example.com")
    app.dependency_overrides[get_current_customer] = lambda: other
    try:
        r = await client.post(f"/api/v1/orders/{order.id}/review", json={"rating": 5})
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 404


@pytest.mark.parametrize("bad", [0, 6, -1])
async def test_review_rejects_bad_rating(client, db_session, app, delivered_order_factory, bad):
    user, order = await delivered_order_factory(db_session)
    app.dependency_overrides[get_current_customer] = lambda: user
    try:
        r = await client.post(f"/api/v1/orders/{order.id}/review", json={"rating": bad})
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 422
```

Add `delivered_order_factory`, `pending_order_factory`, and `customer_factory` to `conftest.py` if not already present. They should produce `(User, Order)` tuples for the requested status, reusing the `_seed_customer` / `_seed_order` patterns from Task 2.1.

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Create `schemas/reviews.py`**

```python
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from pydantic import BaseModel, Field


class OrderReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class OrderReviewRead(BaseModel):
    rating: int
    comment: str | None
```

- [ ] **Step 4: Extend `schemas/orders.py`** — add `review: OrderReviewRead | None = None` to the `OrderRead` response model (look at the actual schema file and adapt to its naming).

- [ ] **Step 5: Add the POST route + populate review on GET**

In `backend/app/src/app/api/orders.py`:

```python
from app.models.commerce import Review
from app.schemas.reviews import OrderReviewCreate, OrderReviewRead


@router.post("/{order_id}/review", response_model=OrderReviewRead)
async def create_order_review(
    order_id: int,
    body: OrderReviewCreate,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
):
    profile = await _customer_profile_for_user(session, current_user.id)
    order = await _get_owned_order(session, profile.id, order_id)  # 404 if not owned
    if order.status != OrderStatus.Delivered:
        raise HTTPException(status_code=409, detail={"error": "order_not_delivered"})
    existing = (await session.exec(select(Review).where(Review.order_id == order.id))).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail={"error": "review_exists"})
    review = Review(
        customer_profile_id=profile.id,
        order_id=order.id,
        store_id=order.store_id,
        rating=body.rating,
        comment=body.comment,
    )
    session.add(review)
    await session.commit()
    return OrderReviewRead(rating=review.rating, comment=review.comment)
```

In the existing `GET /orders/{id}` handler, after fetching the order, also fetch the review (for the owning customer only):

```python
review_row = (await session.exec(select(Review).where(Review.order_id == order.id))).first()
response.review = (
    OrderReviewRead(rating=review_row.rating, comment=review_row.comment)
    if review_row is not None else None
)
```

Use whatever helper / response builder already exists in `orders.py`; the helper functions `_get_owned_order` and the response builder may have different names — adapt to the file.

- [ ] **Step 6: Tests pass, lint, commit**

```bash
cd backend/app && uv run pytest tests/test_order_reviews.py -v
uv run ruff check . && uv run mypy .
git add backend/app/src/app/schemas/reviews.py backend/app/src/app/schemas/orders.py backend/app/src/app/api/orders.py backend/app/tests/test_order_reviews.py backend/app/tests/conftest.py
git commit -m "feat(orders): allow customers to review delivered orders"
```

---

### Task 3.5: Backend — Support contact endpoint

**Files:**
- Modify: `backend/app/src/app/core/config.py` (add `SUPPORT_EMAIL`)
- Modify: `backend/app/src/app/worker.py` (add Celery task `send_support_email`)
- Modify: `backend/app/src/app/api/customers.py` (add route)
- Create: `backend/app/tests/test_customer_support.py`

- [ ] **Step 1: Add config**

In `core/config.py`:

```python
SUPPORT_EMAIL: str = "support@khanabazaar.example"
```

Document the env var in `docs/development_guide.md` if there's an env-vars table.

- [ ] **Step 2: Add Celery task**

In `worker.py` (reuse the pattern from order/OTP email tasks):

```python
@celery_app.task(name="send_support_email")
def send_support_email(customer_email: str, subject: str, message: str) -> None:
    from app.core.email import send_email
    send_email(
        to=settings.SUPPORT_EMAIL,
        subject=f"[Support] {subject}",
        body=f"From: {customer_email}\n\n{message}",
    )
```

- [ ] **Step 3: Add route**

In `api/customers.py`:

```python
from app.worker import send_support_email


class SupportMessage(BaseModel):
    subject: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)


@router.post("/me/support", status_code=202)
async def send_support_message(
    body: SupportMessage,
    current_user: User = Depends(get_current_customer),
):
    send_support_email.delay(current_user.email, body.subject, body.message)
    return {"queued": True}
```

- [ ] **Step 4: Test**

```python
# backend/app/tests/test_customer_support.py
import pytest
from httpx import AsyncClient
from unittest.mock import patch

from app.core.security import get_current_customer
from app.models.base import User, UserRole
from app.models.profile import CustomerProfile

pytestmark = pytest.mark.asyncio


async def test_support_queues_email(client: AsyncClient, db_session, app):
    user = User(email="s@example.com", role=UserRole.Customer, is_active=True)
    db_session.add(user)
    await db_session.flush()
    db_session.add(CustomerProfile(user_id=user.id, first_name="S"))
    await db_session.commit()
    app.dependency_overrides[get_current_customer] = lambda: user
    with patch("app.api.customers.send_support_email") as task:
        try:
            r = await client.post(
                "/api/v1/customers/me/support",
                json={"subject": "hi", "message": "hello"},
            )
        finally:
            app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 202
    task.delay.assert_called_once_with("s@example.com", "hi", "hello")
```

- [ ] **Step 5: Run + lint + commit**

```bash
uv run pytest tests/test_customer_support.py -v && uv run ruff check . && uv run mypy .
git add backend/app/src/app/core/config.py backend/app/src/app/worker.py backend/app/src/app/api/customers.py backend/app/tests/test_customer_support.py
git commit -m "feat(customers): add POST /customers/me/support contact endpoint"
```

---

### Task 3.6: Frontend — Profile page rewrite

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/account/profile/page.tsx`
- Modify: `frontend/src/app/(customer)/[locale]/account/profile/page.module.css`
- Create: `frontend/src/components/PhoneVerifyModal.tsx`
- Create: `frontend/src/components/PhoneVerifyModal.module.css`
- Modify: `frontend/src/types/index.ts` (extend `CustomerProfile`)

- [ ] **Step 1: Extend `CustomerProfile` type**

In `frontend/src/types/index.ts`, add to `CustomerProfile`:

```ts
date_of_birth: string | null;
preferred_language: string | null;
marketing_opt_in: boolean;
notify_order_email: boolean;
notify_order_sms: boolean;
phone_verified_at: string | null;
```

- [ ] **Step 2: Implement `PhoneVerifyModal`**

```tsx
"use client";
import { useState } from "react";
import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import { post } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import type { CustomerProfile } from "@/types";
import styles from "./PhoneVerifyModal.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
  onVerified: (profile: CustomerProfile) => void;
}

export default function PhoneVerifyModal({ open, onClose, onVerified }: Props) {
  const t = useTranslations("Account.profile.phoneVerify");
  const { token } = useAuth();
  const [step, setStep] = useState<"request" | "verify">("request");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestOtp = async () => {
    if (!token) return;
    setBusy(true); setError(null);
    try {
      await post("/api/v1/customers/me/phone/otp/request", { phone }, token);
      setStep("verify");
    } catch (e) {
      const detail = (e as { detail?: { error?: string } }).detail?.error;
      setError(t(`error.${detail ?? "generic"}`));
    } finally { setBusy(false); }
  };

  const verifyOtp = async () => {
    if (!token) return;
    setBusy(true); setError(null);
    try {
      const next = await post<CustomerProfile>(
        "/api/v1/customers/me/phone/otp/verify",
        { phone, code },
        token,
      );
      onVerified(next);
      onClose();
    } catch (e) {
      const detail = (e as { detail?: { error?: string } }).detail?.error;
      setError(t(`error.${detail ?? "generic"}`));
    } finally { setBusy(false); }
  };

  return (
    <Modal isOpen={open} onClose={onClose} title={t("title")}>
      {step === "request" && (
        <div className={styles.body}>
          <label>{t("phoneLabel")}</label>
          <input className={styles.input} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91…" />
          <button className="btn btn-primary" disabled={busy || !phone} onClick={requestOtp}>{t("sendCode")}</button>
        </div>
      )}
      {step === "verify" && (
        <div className={styles.body}>
          <p>{t("sentTo", { phone })}</p>
          <label>{t("codeLabel")}</label>
          <input className={styles.input} value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={6} />
          <button className="btn btn-primary" disabled={busy || code.length !== 6} onClick={verifyOtp}>{t("verify")}</button>
        </div>
      )}
      {error && <div className={styles.error}>{error}</div>}
    </Modal>
  );
}
```

CSS keys (`.body`, `.input`, `.error`) — minimal, mirror existing modal styles.

If the existing `Modal` component takes different props (e.g., `onRequestClose`), adapt accordingly.

- [ ] **Step 3: Add `Account.profile.phoneVerify.*` keys**

```json
"phoneVerify": {
  "title": "Verify your phone",
  "phoneLabel": "Phone (with country code)",
  "codeLabel": "Enter the 6-digit code",
  "sendCode": "Send code",
  "verify": "Verify",
  "sentTo": "We sent a code to {phone}.",
  "error": {
    "generic": "Something went wrong. Try again.",
    "phone_invalid": "That phone number doesn't look right.",
    "phone_already_in_use": "That number is already linked to another account.",
    "otp_invalid": "That code is incorrect or expired."
  }
}
```

- [ ] **Step 4: Rewrite Profile page** to add avatar chip, DOB input, verified badges, stats card, default-address card, "Verify phone" button.

(Detailed sketch — keep the existing first/last name + email fields; insert the new pieces around them.)

```tsx
const initials = (firstName.charAt(0) + (lastName.charAt(0) ?? "")).toUpperCase();
const stableColor = `hsl(${[...email].reduce((a, c) => a + c.charCodeAt(0), 0) % 360}deg 60% 50%)`;

<div className={styles.avatar} style={{ background: stableColor }}>{initials}</div>

<div className={styles.field}>
  <label htmlFor="dob">{t("dobLabel")}</label>
  <input id="dob" type="date" className={styles.input}
         value={profileForm.date_of_birth ?? ""}
         onChange={(e) => setProfileForm((f) => ({ ...f, date_of_birth: e.target.value || null }))} />
</div>

<div className={styles.verifyRow}>
  <span>{profile.phone ?? "—"}</span>
  {profile.phone_verified_at ? (
    <span className={styles.verifiedBadge}>✓ {t("verified")}</span>
  ) : (
    <button className="btn btn-outline" type="button" onClick={() => setVerifyOpen(true)}>
      {t("verifyPhone")}
    </button>
  )}
</div>

<aside className={styles.statsAside}>
  <h3>{t("statsTitle")}</h3>
  <dl>
    <dt>{t("memberSince")}</dt><dd>{new Date(profile.created_at ?? "").toLocaleDateString()}</dd>
    <dt>{t("totalOrders")}</dt><dd>{stats?.orders_this_month ?? "—"}</dd>
    <dt>{t("lifetimeSpend")}</dt><dd>₹{stats?.lifetime_spend.toFixed(0) ?? "—"}</dd>
  </dl>
</aside>
```

Wire `PhoneVerifyModal` via `open={verifyOpen}`, `onVerified={(next) => setProfile(next)}`. `PATCH /api/v1/customers/me` now needs to send `date_of_birth` when the field is touched.

> If `CustomerProfile` doesn't yet carry `created_at`, "Member since" can be derived from the user's `created_at` available on `dbUser`.

- [ ] **Step 5: Lint, smoke, commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src/app/\(customer\)/\[locale\]/account/profile frontend/src/components/PhoneVerifyModal.tsx frontend/src/components/PhoneVerifyModal.module.css frontend/src/types/index.ts frontend/messages
git commit -m "feat(account): enrich /account/profile with verification, DOB, stats"
```

---

### Task 3.7: Frontend — Preferences page (real toggles)

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/account/preferences/page.tsx`

- [ ] **Step 1: Replace stub with real form** wired to `PATCH /api/v1/customers/me/preferences`.

```tsx
"use client";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { get, patch } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import LocaleSwitcher from "@/components/LocaleSwitcher";
import type { CustomerProfile } from "@/types";
import styles from "./page.module.css";

const LANGS = ["en", "hi", "mr", "gu", "pa"] as const;

export default function PreferencesPage() {
  const t = useTranslations("Account.preferences");
  const { token } = useAuth();
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    get<CustomerProfile>("/api/v1/customers/me", token).then(setProfile);
  }, [token]);

  const save = async (patchBody: Partial<CustomerProfile>) => {
    if (!token) return;
    setBusy(true);
    try {
      const next = await patch<CustomerProfile>(
        "/api/v1/customers/me/preferences", patchBody, token,
      );
      setProfile(next);
    } finally { setBusy(false); }
  };

  if (!profile) return <div className={styles.empty}>{t("loading")}</div>;

  return (
    <div className={styles.page}>
      <section className={styles.section}>
        <h2 className={styles.title}>{t("languageTitle")}</h2>
        <p className={styles.subtitle}>{t("languageSubtitle")}</p>
        <select value={profile.preferred_language ?? ""}
                onChange={(e) => save({ preferred_language: e.target.value || null })}
                disabled={busy}>
          <option value="">{t("languageDefault")}</option>
          {LANGS.map((l) => <option key={l} value={l}>{t(`lang.${l}`)}</option>)}
        </select>
        <div style={{ marginTop: 16 }}><LocaleSwitcher /></div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.title}>{t("notificationsTitle")}</h2>
        <label><input type="checkbox" checked={profile.notify_order_email}
                       onChange={(e) => save({ notify_order_email: e.target.checked })} />
          {t("notifyOrderEmail")}</label>
        <label><input type="checkbox" checked={profile.notify_order_sms}
                       onChange={(e) => save({ notify_order_sms: e.target.checked })} />
          {t("notifyOrderSms")}</label>
        <label><input type="checkbox" checked={profile.marketing_opt_in}
                       onChange={(e) => save({ marketing_opt_in: e.target.checked })} />
          {t("marketingOptIn")}</label>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Extend `Account.preferences.*` keys** with `loading`, `languageDefault`, `lang.{en,hi,mr,gu,pa}`, `notifyOrderEmail`, `notifyOrderSms`, `marketingOptIn`.

- [ ] **Step 3: Lint + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src/app/\(customer\)/\[locale\]/account/preferences frontend/messages
git commit -m "feat(account): wire /account/preferences to PATCH endpoint"
```

---

### Task 3.8: Frontend — Addresses page polish (digipin, map preview, geolocate)

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/account/addresses/page.tsx`
- Modify: `frontend/src/app/(customer)/[locale]/account/addresses/page.module.css`

- [ ] **Step 1: Show DIGIPIN + coords on each card.** Inside the address-card render, below `formatAddress(...)`:

```tsx
{customerAddress.address.digipin && (
  <div className={styles.digipin}>DIGIPIN: <span className={styles.mono}>{customerAddress.address.digipin}</span></div>
)}
{customerAddress.address.latitude !== null && (
  <div className={styles.coords}>
    {customerAddress.address.latitude.toFixed(5)}, {customerAddress.address.longitude?.toFixed(5)}
  </div>
)}
<button type="button" className={styles.textButton} onClick={() => setMapPreview(customerAddress)}>{t("viewOnMap")}</button>
```

- [ ] **Step 2: Add a map-preview modal**

```tsx
{mapPreview && (
  <Modal isOpen={true} onClose={() => setMapPreview(null)} title={mapPreview.label ?? t("addressFallbackLabel")}>
    <MapPicker
      value={{ lat: mapPreview.address.latitude!, lng: mapPreview.address.longitude! }}
      onChange={() => {}}
      readOnly
    />
  </Modal>
)}
```

If `MapPicker` doesn't accept `readOnly` today, add the prop (default false) and gate the drag/click handlers on it.

- [ ] **Step 3: Add "Use current location" button** inside the add/edit form, above `<AddressFields />`:

```tsx
const useCurrentLocation = async () => {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(async (pos) => {
    const { latitude, longitude } = pos.coords;
    try {
      const place = await get<{ address_line1: string; city: string; state: string; pincode: string; country: string; latitude: number; longitude: number }>(
        `/api/v1/geo/reverse?lat=${latitude}&lng=${longitude}`,
      );
      setAddressForm((curr) => curr && ({
        ...curr,
        address: { ...curr.address, ...place, location_source: "geocoded" },
      }));
    } catch { /* fall through — user can still edit manually */ }
  });
};
```

Add the button:

```tsx
<button type="button" className={styles.textButton} onClick={useCurrentLocation}>{t("useCurrentLocation")}</button>
```

- [ ] **Step 4: CSS + i18n additions**

CSS (append):
```css
.digipin, .coords { font-size: var(--font-xs); color: var(--color-neutral-500); margin-top: 4px; }
.mono { font-family: var(--font-mono, monospace); }
```

i18n keys (under `Account.addresses`):
```json
"viewOnMap": "View on map",
"useCurrentLocation": "Use current location"
```

- [ ] **Step 5: Lint + smoke + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src/app/\(customer\)/\[locale\]/account/addresses frontend/src/components/MapPicker.tsx frontend/messages
git commit -m "feat(account): polish addresses page with digipin + map preview + geolocate"
```

---

### Task 3.9: Frontend — Order review UI

**Files:**
- Create: `frontend/src/components/orders/OrderReviewForm.tsx`
- Create: `frontend/src/components/orders/OrderReviewForm.module.css`
- Modify: `frontend/src/components/orders/OrderActionButtons.tsx` (add Rate button)
- Modify: `frontend/src/types/index.ts` (add `review: OrderReview | null` on `Order`)
- Modify: `frontend/src/lib/orders.ts` (add `submitReview`)

- [ ] **Step 1: Extend types**

In `types/index.ts`, add:
```ts
export interface OrderReview { rating: number; comment: string | null; }
```
and append `review: OrderReview | null;` to the `Order` interface.

- [ ] **Step 2: Add `submitReview` fetcher**

In `lib/orders.ts`:
```ts
export async function submitReview(token: string, orderId: number, rating: number, comment?: string): Promise<{ rating: number; comment: string | null }> {
  return post("/api/v1/orders/" + orderId + "/review", { rating, comment: comment ?? null }, token);
}
```

- [ ] **Step 3: Create `OrderReviewForm.tsx`**

```tsx
"use client";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { submitReview } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import type { Order } from "@/types";
import styles from "./OrderReviewForm.module.css";

interface Props { order: Order; onSubmitted: (next: Order) => void; }

export default function OrderReviewForm({ order, onSubmitted }: Props) {
  const t = useTranslations("Order.review");
  const { token } = useAuth();
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || rating < 1) return;
    setBusy(true); setError(null);
    try {
      await submitReview(token, order.id, rating, comment || undefined);
      onSubmitted({ ...order, review: { rating, comment: comment || null } });
    } catch (err) {
      setError((err as { detail?: { error?: string } }).detail?.error ?? t("error"));
    } finally { setBusy(false); }
  };

  return (
    <form className={styles.form} onSubmit={send}>
      <div className={styles.stars}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" className={n <= rating ? styles.starActive : styles.star}
                  onClick={() => setRating(n)} aria-label={t("starAria", { n })}>★</button>
        ))}
      </div>
      <textarea className={styles.textarea} value={comment} onChange={(e) => setComment(e.target.value)}
                placeholder={t("commentPlaceholder")} maxLength={2000} />
      <button className="btn btn-primary" disabled={busy || rating < 1}>{t("submit")}</button>
      {error && <div className={styles.error}>{error}</div>}
    </form>
  );
}
```

CSS: `.form { display: flex; flex-direction: column; gap: 8px; } .stars { display: flex; gap: 4px; } .star, .starActive { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--color-neutral-300); } .starActive { color: var(--color-warning-500); } .textarea { min-height: 80px; }`

- [ ] **Step 4: Add Rate button in `OrderActionButtons`**

Inside `OrderActionButtons.tsx`, add a Modal-trigger for the review form when:
```ts
const canRate = role === "customer" && order.status === "delivered" && order.review === null;
```

Render a `<button>{t("rateOrder")}</button>` that opens a `<Modal>` containing `<OrderReviewForm order={order} onSubmitted={(next) => { onChange(next); setOpen(false); }} />`.

- [ ] **Step 5: Add `Order.review.*` + `Order.actions.rateOrder` i18n keys** to all message files.

```json
"review": {
  "rateOrder": "Rate this order",
  "submit": "Submit review",
  "commentPlaceholder": "What did you think?",
  "starAria": "{n} stars",
  "error": "Could not submit your review. Try again.",
  "yourRating": "Your rating: {rating}/5"
},
"actions": { "rateOrder": "Rate" }
```

- [ ] **Step 6: Lint, smoke, commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src/components/orders/OrderReviewForm.tsx frontend/src/components/orders/OrderReviewForm.module.css frontend/src/components/orders/OrderActionButtons.tsx frontend/src/types/index.ts frontend/src/lib/orders.ts frontend/messages
git commit -m "feat(orders): customer order rating + review form"
```

---

### Task 3.10: Frontend — Wire support form to backend

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/account/support/page.tsx`

- [ ] **Step 1: Replace the `console.log` submit with a real POST**

```tsx
import { post } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";

const { token } = useAuth();
const submit = async (e: React.FormEvent<HTMLFormElement>) => {
  e.preventDefault();
  if (!token) return;
  try {
    await post("/api/v1/customers/me/support", { subject, message }, token);
    setSent(true);
    setSubject(""); setMessage("");
  } catch {
    setSent(false);
    setError(t("sendError"));
  }
};
```

Add a small `error` state + render it under the form.

- [ ] **Step 2: Lint + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src/app/\(customer\)/\[locale\]/account/support
git commit -m "feat(account): wire support contact form to backend"
```

---

### Task 3.11: Frontend — Recently-viewed hook + rail

**Files:**
- Create: `frontend/src/lib/recentlyViewed.ts`
- Create: `frontend/src/components/RecentlyViewedRail.tsx`
- Create: `frontend/src/components/RecentlyViewedRail.module.css`
- Modify: `frontend/src/components/ProductDetail/ProductDetail.tsx` (push entry on mount — adapt to actual filename)
- Modify: `frontend/src/app/(customer)/[locale]/account/page.tsx` (mount rail below order-again)

- [ ] **Step 1: Create the hook**

```ts
// frontend/src/lib/recentlyViewed.ts
const KEY = "kb_recently_viewed";
const CAP = 20;

export interface RecentlyViewedEntry {
  product_id: number;
  store_id: number;
  name: string;
  image_url: string | null;
  viewed_at: string;
}

function readSafe(): RecentlyViewedEntry[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.slice(0, CAP) : [];
  } catch {
    localStorage.removeItem(KEY);
    return [];
  }
}

export function getRecentlyViewed(): RecentlyViewedEntry[] {
  if (typeof window === "undefined") return [];
  return readSafe();
}

export function pushRecentlyViewed(entry: Omit<RecentlyViewedEntry, "viewed_at">) {
  if (typeof window === "undefined") return;
  const next: RecentlyViewedEntry[] = [
    { ...entry, viewed_at: new Date().toISOString() },
    ...readSafe().filter((e) => e.product_id !== entry.product_id),
  ].slice(0, CAP);
  localStorage.setItem(KEY, JSON.stringify(next));
}
```

- [ ] **Step 2: Push on ProductDetail mount**

In the product detail component (`frontend/src/components/ProductDetail/ProductDetail.tsx` or equivalent — grep for the page that renders `<ProductDetail>`), inside a `useEffect`:

```ts
useEffect(() => {
  if (!product) return;
  pushRecentlyViewed({
    product_id: product.id, store_id: store.id, name: product.name, image_url: product.image_url ?? null,
  });
}, [product?.id, store?.id]);
```

- [ ] **Step 3: Create the rail**

```tsx
"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { getRecentlyViewed, type RecentlyViewedEntry } from "@/lib/recentlyViewed";
import styles from "./RecentlyViewedRail.module.css";

export default function RecentlyViewedRail() {
  const t = useTranslations("Account.dashboard");
  const [items, setItems] = useState<RecentlyViewedEntry[]>([]);
  useEffect(() => { setItems(getRecentlyViewed().slice(0, 5)); }, []);
  if (items.length === 0) return null;
  return (
    <section className={styles.rail}>
      <h2 className={styles.title}>{t("recentlyViewed")}</h2>
      <div className={styles.list}>
        {items.map((it) => (
          <Link key={it.product_id} href={`/stores/${it.store_id}/products/${it.product_id}`} className={styles.card}>
            {it.image_url && <img src={it.image_url} alt="" referrerPolicy="no-referrer" />}
            <span>{it.name}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
```

CSS — small horizontally-scrollable list (mirrors order-again rail look).

- [ ] **Step 4: Mount on dashboard**

In `account/page.tsx` (Task 2.5), import and render `<RecentlyViewedRail />` after the order-again section.

- [ ] **Step 5: Add the `recentlyViewed` translation key.**

Add to `Account.dashboard` in each message file: `"recentlyViewed": "Recently viewed"`.

- [ ] **Step 6: Lint + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src/lib/recentlyViewed.ts frontend/src/components/RecentlyViewedRail.tsx frontend/src/components/RecentlyViewedRail.module.css frontend/src/components/ProductDetail frontend/src/app/\(customer\)/\[locale\]/account/page.tsx frontend/messages
git commit -m "feat(account): add recently-viewed rail to dashboard"
```

---

### Task 3.12: Final lint/test/PR for Phase 3

- [ ] **Step 1: Run full test + lint matrix**

```bash
cd backend/app && uv run pytest -v && uv run ruff check . && uv run mypy .
cd ../../frontend && npm run lint && npx tsc --noEmit
```
Expected: everything green.

- [ ] **Step 2: Push + open PR**

```bash
git push
gh pr create --title "feat(account): profile + preferences + reviews + support + recently-viewed" --body "$(cat <<'EOF'
## Summary
- DB migration: add `preferred_language`, `marketing_opt_in`, `notify_order_email`, `notify_order_sms`, `phone_verified_at` to `customerprofile`; partial unique on `review.order_id`; CHECK rating BETWEEN 1 AND 5.
- New endpoints: `PATCH /customers/me/preferences`, `POST /customers/me/phone/otp/{request,verify}`, `POST /orders/{id}/review`, `POST /customers/me/support`.
- Frontend: enriched profile (avatar chip, DOB, verified badges, stats), preferences with real toggles, addresses with digipin + map preview + geolocate, order rating form, support form wired to backend, recently-viewed rail.

Spec: docs/superpowers/specs/2026-05-14-customer-dashboard-redesign-design.md (Part 3).

## Test plan
- [ ] All backend tests pass; ruff + mypy clean.
- [ ] Frontend lint + tsc clean.
- [ ] Phone verification: request → receive OTP (console SMS provider) → verify → badge appears.
- [ ] Phone verification: number already on another account → 409 surfaced as inline error.
- [ ] Preferences: language change persists; toggles persist; partial PATCH preserves untouched fields.
- [ ] Order rating: rate a delivered order; second attempt blocked; non-delivered order blocked.
- [ ] Addresses: digipin + coords visible; map preview opens; "use current location" backfills city/state.
- [ ] Support: form submission → 202 → Celery email task enqueued.
- [ ] Recently-viewed: visit a product, return to /account, see it on the rail.
EOF
)"
```

- [ ] **Step 3: Wait for user approval. Merge with `gh pr merge <N> --merge` once approved.**

---

## Self-Review Notes

- Reorder feature is intentionally not implemented (deferred per spec).
- Avatar uploading is deferred (initials only).
- `Favorite` and `Review.product_id`/`store_id` columns exist but no UI surfaces them in this plan.
- `Sign out everywhere`, account deletion, dark mode, theme — all deferred.
- The plan reuses the existing `Review` table; do NOT add a separate `order_reviews` table during execution.
- Migration target table names are SQLModel defaults: `customerprofile`, `customeraddress`, `order`, `orderitem`, `review`. Verify with `\d <name>` in psql before writing migration SQL by hand.
