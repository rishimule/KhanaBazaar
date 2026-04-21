# Become Seller Landing Page Design

## Context

Khana Bazaar already has a complete seller signup and onboarding flow documented in
`docs/seller_signup.md`. The flow lives at `/seller/signup` and includes email OTP
verification, a six-step seller application, pending admin approval, rejection
resubmission, and dashboard access after approval.

The new page is a public acquisition page for sellers. It should explain why a
local shop owner should apply, set accurate expectations about verification, and
route qualified sellers into the existing signup wizard.

## Goals

- Create a polished public `/sell` landing page for prospective sellers.
- Lead with local trust and community, aimed first at neighborhood kirana and
  grocery stores while still welcoming pharmacy, electronics, and general stores.
- Make the approval-based onboarding flow clear before sellers provide GST,
  FSSAI, and bank details.
- Add obvious entry points from the navbar, homepage, and footer.
- Reuse existing frontend conventions: Next.js App Router, CSS Modules, design
  tokens, no Tailwind.

## Non-Goals

- Do not change seller signup, OTP, approval, dashboard, or backend behavior.
- Do not add fake seller counts, revenue claims, order-volume claims, or other
  unsupported metrics.
- Do not introduce external image licensing or remote image dependencies in the
  first implementation.
- Do not build a multi-page seller marketing site.

## Route And Navigation

### New Route

- Add `frontend/src/app/sell/page.tsx`.
- Add `frontend/src/app/sell/page.module.css`.
- `/sell` is a public route. It does not require authentication and does not call
  backend APIs.

### Calls To Action

- Primary CTA: `Apply to sell` -> `/seller/signup`.
- Secondary CTA: `See how it works` -> `#how-it-works` on the same page.
- Final CTA: `Start your seller application` -> `/seller/signup`.

### Existing Entry Points

- Navbar:
  - Add a `Sell` link for logged-out users and customer users.
  - Keep the existing `Seller` dashboard link for seller users.
  - Keep admin users focused on the admin link.
- Homepage:
  - Change the secondary hero CTA to `Sell on Khana Bazaar` and link it to
    `/sell`.
- Footer:
  - Convert the current `For Sellers` placeholder in the Company column into a
    real link to `/sell`.

## Page Structure

The page should be a single mobile-first landing page with these sections.

### 1. Hero

Purpose: make local shop owners immediately recognize that the page is for them.

Content:

- Eyebrow: `For local stores`
- H1: `Bring your neighborhood store online`
- Body: `Khana Bazaar helps kiranas, pharmacies, electronics shops, and general stores reach nearby customers while keeping control of products, prices, and stock.`
- Support line: `Apply in a few minutes. We review every seller application before stores go live, usually within 1-2 business days.`
- Primary CTA: `Apply to sell`
- Secondary CTA: `See how it works`

Visual:

- Desktop: two-column layout with copy on the left and a storefront/dashboard
  visual on the right.
- Mobile: single-column layout with the CTA visible without excessive scrolling.
- Use a CSS/HTML illustration for the first pass: shop shelves, counter/order
  panel, and Khana Bazaar accents. This avoids asset sourcing and keeps the page
  self-contained.

### 2. Value Cards

Purpose: give the page the confidence of a merchant platform without unsupported
numeric claims.

Cards:

- `Local reach`: Help nearby shoppers discover your store when they need daily
  essentials.
- `Inventory control`: Manage products, stock, and pricing from your seller
  dashboard.
- `Verified sellers`: Every seller application is reviewed before stores go
  live.
- `Indian commerce ready`: Built around GST, FSSAI, IFSC, and UPI-oriented local
  commerce workflows.

These are proof-style cards, not statistical claims.

### 3. How It Works

Purpose: reduce confusion about the approval process.

Anchor id: `how-it-works`

Steps:

1. `Verify your email`: Request an OTP and confirm ownership of your email.
2. `Submit business details`: Add personal, business, compliance, and bank
   details in the existing six-step wizard.
3. `Wait for review`: Khana Bazaar reviews every application. Most reviews are
   expected to take 1-2 business days.
4. `Start selling`: Once approved, access the seller dashboard to create stores
   and manage inventory.

### 4. Store Categories

Purpose: make the page inclusive beyond groceries while still feeling local.

Categories:

- Grocery and kirana stores
- Pharmacy and wellness shops
- Electronics and mobile accessory shops
- General stores and neighborhood essentials

The section should not imply all categories are operationally identical. It only
communicates who can apply.

### 5. Dashboard Preview

Purpose: show that the seller experience is practical, not just promotional.

Use a CSS-built dashboard mockup that suggests:

- Store status
- Inventory rows
- Price and stock controls
- Product categories
- Pending or approved verification state

This mockup is illustrative only and should not create new product promises that
do not exist in the seller dashboard.

### 6. Checklist

Purpose: help sellers prepare before entering the wizard.

Content:

- Verified email and mobile number
- Business name, category, and address
- GST number
- FSSAI license
- Bank account number and IFSC

Note: the current wizard requires FSSAI. The landing page should avoid saying
"only for food sellers" unless the signup flow is changed later.

### 7. FAQ

Purpose: answer conversion-blocking questions without requiring another page.

Static FAQ rows are sufficient unless an accordion pattern already exists.

Questions:

- `Is approval instant?`
  - No. Every application is reviewed before a store can go live. The page should
    say review usually takes 1-2 business days.
- `What documents do I need?`
  - Email, mobile number, business details, GST, FSSAI, bank account number, and
    IFSC.
- `Can I update my application if it is rejected?`
  - Yes. Rejected sellers can edit details and resubmit from the pending page.
- `What happens after approval?`
  - Approved sellers are routed to the seller dashboard, where they can create
    stores and manage inventory.
- `Do I control my products and prices?`
  - Yes. Sellers manage local inventory and pricing from the seller dashboard.
- `Which businesses can apply?`
  - Grocery, pharmacy, electronics, and general local stores can apply.

### 8. Final CTA

Purpose: close the page with a clear action after objections have been handled.

Copy:

- Heading: `Ready to bring your store online?`
- Body: `Start your seller application and keep your business details ready.`
- CTA: `Start your seller application` -> `/seller/signup`

## Visual Direction

- Overall tone: friendly neighborhood/local business with premium polish.
- Use existing saffron primary and emerald accent tokens, balanced with white and
  neutral surfaces.
- Avoid a page that reads as only orange. Use neutral backgrounds, green accents,
  and restrained warm highlights.
- Avoid decorative gradient orbs and purely abstract visuals.
- Use compact, readable mobile sections and richer desktop layouts.
- Cards should use the existing design token scale, with `8px` radius preferred
  for compact UI surfaces unless current component patterns require a larger
  radius.
- Do not nest cards inside other cards.
- Do not use large claims or corporate ad-platform language.

## Behavior

- `/sell` does not depend on auth state for rendering its content.
- CTAs use normal Next.js `Link` navigation.
- The secondary hero CTA links to `#how-it-works`.
- FAQ rows are static content in the first implementation.
- Existing `/seller/signup` remains the only seller application wizard.

## Data Flow

- No new API calls.
- No backend schema or endpoint changes.
- No auth changes.
- No seller approval workflow changes.

## Accessibility And Responsive Requirements

- The page must work well at mobile widths first.
- CTA text must not wrap awkwardly or overflow buttons.
- The hero CTA should be visible quickly on mobile.
- Use semantic sections and headings.
- Use readable color contrast against warm and dark backgrounds.
- Decorative mockup elements should not be required to understand the page.

## Testing

Run from `frontend/`:

- `npm run lint`
- `npm run build`

Manual checks:

- Visit `/sell` on desktop and mobile widths.
- Confirm primary and final CTAs route to `/seller/signup`.
- Confirm `See how it works` scrolls to the process section.
- Confirm navbar link visibility for logged-out, customer, seller, and admin
  states as much as local auth setup allows.
- Confirm homepage secondary CTA points to `/sell`.
- Confirm footer `For Sellers` links to `/sell`.

## Open Questions Resolved

- Route: `/sell`.
- Landing page length: single long landing page, concise but trust-building.
- Tone: local trust and community.
- Claims: use benefit cards, not fake metrics.
- Hero CTA: `Apply to sell`.
- Approval expectation: mention 1-2 business days in hero support copy, process,
  and FAQ.
- Checklist: include it.
- Visual assets: first pass uses CSS/HTML visuals rather than external images.
