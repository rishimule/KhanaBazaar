<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Home Page Refresh Design

## Context

The current Home page at `frontend/src/app/page.tsx` is a centered hero with
three feature cards and a basic store grid. It works functionally, but the first
impression is generic and does not yet communicate the premium, local
marketplace position Khana Bazaar needs for customers and sellers.

The refresh should improve the Home page only. It should keep the existing
Next.js App Router, React client component, CSS Modules, design tokens, auth
state, and store API call.

## Goals

- Make the Home page feel like a trustworthy premium grocery marketplace with
  subtle local Indian bazaar warmth.
- Put customer conversion first: clear value, clear shopping CTA, visible nearby
  store discovery.
- Keep a seller entry point visible without making the page a seller landing
  page.
- Improve layout richness using CSS and HTML, without external images or a new
  styling framework.
- Preserve existing behavior for logged-in and logged-out users.

## Non-Goals

- Do not change backend APIs, auth behavior, cart behavior, or store detail
  pages.
- Do not add unsupported metrics, delivery-time guarantees, fake ratings, or
  fake store counts.
- Do not introduce Tailwind, new UI libraries, remote image dependencies, or
  broad design token changes.
- Do not redesign the navbar or footer as part of this task.

## Page Structure

### 1. Marketplace Hero

Use a responsive two-column hero.

Left content:

- Badge: `Premium local grocery`
- H1: `Daily essentials from trusted neighborhood stores`
- Body: explain that shoppers can browse nearby stores, compare local inventory,
  and check out through a familiar Indian-market shopping flow.
- Primary CTA:
  - Logged-in users: `Start shopping` -> `/stores`
  - Logged-out users: `Sign in to shop` -> `/login`
- Secondary CTA: `Sell on Khana Bazaar` -> `/sell`
- Trust chips with supported, non-numeric statements:
  - `Pincode-first discovery`
  - `Local seller inventory`
  - `UPI-ready commerce`

Right content:

- Build a CSS/HTML market basket and order preview visual.
- Include produce/essential item rows, a small delivery/location card, and an
  order summary panel.
- The visual is decorative and should not imply unsupported live pricing,
  discounts, or delivery guarantees.

### 2. Benefits Row

Replace the existing feature cards with three compact marketplace benefits:

- `Shop nearby`: find stores serving your area.
- `Fresh essentials`: browse groceries and daily needs from local sellers.
- `Built for mobile`: installable PWA experience for repeated ordering.

Use distinct saffron, emerald, and blue accents so the section does not become a
single-hue orange layout.

### 3. Popular Stores

Keep the existing `stores` API data and auth-aware links.

Improve card hierarchy:

- Store icon or initials treatment.
- Store name as the primary line.
- Address as muted supporting text.
- Status pill: `Open now`.
- CTA hint: `Browse store`.

Add an empty state for when no stores are returned:

- Message: `Stores are being prepared for your area.`
- CTA:
  - Logged-in users: `Browse all stores` -> `/stores`
  - Logged-out users: `Sign in to browse` -> `/login`

### 4. Seller CTA Band

Add a compact full-width band after the store section:

- Heading: `Run a local store?`
- Body: explain that sellers can bring their catalog online and manage local
  inventory.
- CTA: `Become a seller` -> `/sell`

This should be a focused conversion band, not a duplicate of the `/sell` page.

## Visual Direction

- Tone: premium, local, fast, trustworthy.
- Use existing saffron/coral primary colors, emerald accents, and neutral
  surfaces.
- Avoid decorative gradient orbs and abstract-only visuals.
- Keep cards at `8px` radius where possible, using the existing design token
  scale.
- Avoid nested cards. Use section bands and individual cards only.
- Preserve readable type sizes on mobile; do not use viewport-width font
  scaling.
- Use CSS-built visuals and emoji-free UI decoration for a more polished product
  feel.

## Behavior

- Keep `Home` as a client component because it depends on `useAuth` and
  `useEffect`.
- Continue fetching `GET /api/v1/stores/`.
- Continue falling back to an empty store list on API failure.
- Logged-out users should be routed to `/login` from store cards and shopping
  CTAs.
- Logged-in users should be routed to `/stores` or `/stores/[id]`.

## Testing

- Run frontend lint from `frontend/`.
- Run a production build from `frontend/`.
- Start the frontend dev server and inspect the Home page at `/`.
- Verify desktop and mobile responsive layout by checking rendered HTML and, if
  browser tooling is available, viewport screenshots.
