# Become Seller Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public `/sell` landing page that attracts local sellers and routes them into the existing seller signup wizard.

**Architecture:** Add a self-contained public App Router page with a CSS Module and no API calls. Reuse the existing global button classes and design tokens. Update the navbar, homepage, and footer to expose the new route while leaving the existing seller signup and dashboard behavior unchanged.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, CSS Modules, existing Khana Bazaar design tokens.

---

## Files

- Create: `frontend/src/app/sell/page.tsx`
  - Public seller landing page content and section structure.
- Create: `frontend/src/app/sell/page.module.css`
  - Page-specific responsive styling, storefront visual, dashboard mockup, cards, FAQ rows, and CTA bands.
- Modify: `frontend/src/components/Navbar.tsx`
  - Add a public `Sell` nav link for logged-out and customer users.
- Modify: `frontend/src/components/Footer.tsx`
  - Convert the seller-facing company item into a real `/sell` link.
- Modify: `frontend/src/app/page.tsx`
  - Change the homepage secondary hero CTA to route prospective sellers to `/sell`.

## Task 1: Create The `/sell` Route Content

**Files:**
- Create: `frontend/src/app/sell/page.tsx`
- Depends on: `frontend/src/app/sell/page.module.css` from Task 2 for styling

- [ ] **Step 1: Create the route directory**

Run:

```bash
mkdir -p frontend/src/app/sell
```

Expected: command exits with code 0.

- [ ] **Step 2: Add the page component**

Create `frontend/src/app/sell/page.tsx` with this content:

```tsx
import type { Metadata } from "next";
import Link from "next/link";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Become a Seller",
  description:
    "Apply to sell on Khana Bazaar and bring your neighborhood store online for nearby shoppers.",
};

const valueCards = [
  {
    label: "Local reach",
    title: "Be found by nearby shoppers",
    description:
      "Help customers in your neighborhood discover your store when they need groceries, essentials, wellness products, or daily supplies.",
  },
  {
    label: "Inventory control",
    title: "Keep control of your shelves",
    description:
      "Manage products, local pricing, stock, and availability from the seller dashboard as your store changes through the day.",
  },
  {
    label: "Verified sellers",
    title: "Build trust before going live",
    description:
      "Every seller application is reviewed before a store can go live, helping Khana Bazaar stay useful and trusted for local shoppers.",
  },
  {
    label: "Indian commerce ready",
    title: "Built around local business needs",
    description:
      "The signup flow supports GST, FSSAI, IFSC, bank details, and UPI-oriented commerce for Indian neighborhood stores.",
  },
];

const steps = [
  {
    title: "Verify your email",
    description:
      "Request an OTP and confirm ownership of the email address you will use for your seller account.",
  },
  {
    title: "Submit business details",
    description:
      "Add your personal, business, compliance, and bank details in the guided seller application.",
  },
  {
    title: "Wait for review",
    description:
      "Khana Bazaar reviews every application before stores go live. Most reviews are expected to take 1-2 business days.",
  },
  {
    title: "Start selling",
    description:
      "After approval, open your seller dashboard, create your store, and manage inventory for nearby shoppers.",
  },
];

const categories = [
  {
    icon: "KG",
    title: "Grocery and kirana",
    description: "Daily essentials, packaged foods, fresh items, and local household needs.",
  },
  {
    icon: "RX",
    title: "Pharmacy and wellness",
    description: "Neighborhood wellness, health, and personal care shops serving local customers.",
  },
  {
    icon: "EL",
    title: "Electronics accessories",
    description: "Mobile accessories, cables, batteries, and practical electronics for nearby buyers.",
  },
  {
    icon: "GS",
    title: "General stores",
    description: "Mixed local essentials and neighborhood products customers already rely on.",
  },
];

const checklist = [
  "Verified email and mobile number",
  "Business name, category, and address",
  "GST number",
  "FSSAI license",
  "Bank account number and IFSC",
];

const faqs = [
  {
    question: "Is approval instant?",
    answer:
      "No. Every application is reviewed before a store can go live. Reviews are usually expected to take 1-2 business days.",
  },
  {
    question: "What documents do I need?",
    answer:
      "Keep your email, mobile number, business details, GST number, FSSAI license, bank account number, and IFSC ready.",
  },
  {
    question: "Can I update my application if it is rejected?",
    answer:
      "Yes. If an application is rejected, you can edit your details and resubmit them from the seller pending page.",
  },
  {
    question: "What happens after approval?",
    answer:
      "Approved sellers are routed to the seller dashboard, where they can create stores and manage local inventory.",
  },
  {
    question: "Do I control my products and prices?",
    answer:
      "Yes. Sellers manage local inventory, availability, and pricing from the seller dashboard.",
  },
  {
    question: "Which businesses can apply?",
    answer:
      "Grocery, kirana, pharmacy, electronics, and general neighborhood stores can apply to sell on Khana Bazaar.",
  },
];

export default function SellPage() {
  return (
    <>
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <div className={styles.heroCopy}>
            <span className={styles.eyebrow}>For local stores</span>
            <h1 className={styles.heroTitle}>
              Bring your neighborhood store online
            </h1>
            <p className={styles.heroDescription}>
              Khana Bazaar helps kiranas, pharmacies, electronics shops, and
              general stores reach nearby customers while keeping control of
              products, prices, and stock.
            </p>
            <p className={styles.reviewNote}>
              Apply in a few minutes. We review every seller application before
              stores go live, usually within 1-2 business days.
            </p>
            <div className={styles.heroActions}>
              <Link href="/seller/signup" className="btn btn-primary">
                Apply to sell
              </Link>
              <Link href="#how-it-works" className="btn btn-outline">
                See how it works
              </Link>
            </div>
          </div>

          <div className={styles.storefrontVisual} aria-label="Khana Bazaar storefront preview">
            <div className={styles.awning}>
              <span />
              <span />
              <span />
              <span />
            </div>
            <div className={styles.shopSign}>Khana Bazaar Partner</div>
            <div className={styles.shelves}>
              <div className={styles.shelfRow}>
                <span className={styles.productBox} />
                <span className={styles.productJar} />
                <span className={styles.productBoxSmall} />
              </div>
              <div className={styles.shelfRow}>
                <span className={styles.productJar} />
                <span className={styles.productBox} />
                <span className={styles.productBoxSmall} />
              </div>
            </div>
            <div className={styles.counter}>
              <div>
                <span className={styles.counterLabel}>New local order</span>
                <strong>12 items ready</strong>
              </div>
              <span className={styles.orderBadge}>Accepted</span>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.valueSection} aria-labelledby="seller-value-title">
        <div className={styles.sectionInner}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionKicker}>Why sell with us</span>
            <h2 id="seller-value-title">Your store stays local. Your reach gets bigger.</h2>
            <p>
              Khana Bazaar is built for neighborhood commerce: practical seller
              tools, verified onboarding, and a customer experience centered on
              nearby stores.
            </p>
          </div>

          <div className={styles.valueGrid}>
            {valueCards.map((card) => (
              <article key={card.label} className={styles.valueCard}>
                <span>{card.label}</span>
                <h3>{card.title}</h3>
                <p>{card.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="how-it-works" className={styles.processSection} aria-labelledby="how-it-works-title">
        <div className={styles.sectionInner}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionKicker}>How it works</span>
            <h2 id="how-it-works-title">From application to approved store</h2>
            <p>
              The seller flow is straightforward, but every store is reviewed
              before it can serve customers on Khana Bazaar.
            </p>
          </div>

          <div className={styles.stepsGrid}>
            {steps.map((step, index) => (
              <article key={step.title} className={styles.stepCard}>
                <span className={styles.stepNumber}>{index + 1}</span>
                <h3>{step.title}</h3>
                <p>{step.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={styles.categoriesSection} aria-labelledby="categories-title">
        <div className={styles.sectionInner}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionKicker}>Built for neighborhood sellers</span>
            <h2 id="categories-title">Local stores of many kinds can apply</h2>
            <p>
              Lead with your existing store, then manage your digital storefront
              through Khana Bazaar after approval.
            </p>
          </div>

          <div className={styles.categoryGrid}>
            {categories.map((category) => (
              <article key={category.title} className={styles.categoryCard}>
                <span className={styles.categoryIcon}>{category.icon}</span>
                <h3>{category.title}</h3>
                <p>{category.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={styles.dashboardSection} aria-labelledby="dashboard-title">
        <div className={styles.dashboardInner}>
          <div className={styles.dashboardCopy}>
            <span className={styles.sectionKicker}>Seller dashboard</span>
            <h2 id="dashboard-title">Run the online side of your store with clarity</h2>
            <p>
              Once approved, sellers can manage inventory, stock, availability,
              and storefront visibility from their dashboard.
            </p>
            <ul className={styles.featureList}>
              <li>Track available products and total stock</li>
              <li>Manage inventory and storefront visibility</li>
              <li>Keep local pricing and availability up to date</li>
            </ul>
          </div>

          <div className={styles.dashboardMockup} aria-label="Seller dashboard preview">
            <div className={styles.mockupTopbar}>
              <span />
              <span />
              <span />
            </div>
            <div className={styles.mockupStats}>
              <div>
                <span>Total products</span>
                <strong>48</strong>
              </div>
              <div>
                <span>Store status</span>
                <strong>Active</strong>
              </div>
            </div>
            <div className={styles.inventoryTable}>
              <div className={styles.inventoryRow}>
                <span>Rice 5kg</span>
                <strong>In stock</strong>
              </div>
              <div className={styles.inventoryRow}>
                <span>Cooking oil</span>
                <strong>Low stock</strong>
              </div>
              <div className={styles.inventoryRow}>
                <span>Tea pack</span>
                <strong>Available</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.prepSection} aria-labelledby="checklist-title">
        <div className={styles.prepInner}>
          <div>
            <span className={styles.sectionKicker}>Before you apply</span>
            <h2 id="checklist-title">Keep these details ready</h2>
            <p>
              Having your business and bank details nearby makes the seller
              application faster to complete.
            </p>
          </div>
          <ul className={styles.checklist}>
            {checklist.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className={styles.faqSection} aria-labelledby="faq-title">
        <div className={styles.sectionInner}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionKicker}>Questions sellers ask</span>
            <h2 id="faq-title">Clear answers before you start</h2>
          </div>
          <div className={styles.faqList}>
            {faqs.map((faq) => (
              <article key={faq.question} className={styles.faqItem}>
                <h3>{faq.question}</h3>
                <p>{faq.answer}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={styles.finalCta}>
        <div className={styles.finalCtaInner}>
          <span className={styles.sectionKicker}>Ready when you are</span>
          <h2>Ready to bring your store online?</h2>
          <p>Start your seller application and keep your business details ready.</p>
          <Link href="/seller/signup" className="btn btn-primary">
            Start your seller application
          </Link>
        </div>
      </section>
    </>
  );
}
```

- [ ] **Step 3: Run lint to expose the expected missing CSS module failure**

Run:

```bash
cd frontend && npm run lint
```

Expected: FAIL because `./page.module.css` does not exist yet.

- [ ] **Step 4: Commit**

Do not commit yet. This task depends on Task 2 because the new page imports a CSS module that does not exist until Task 2.

## Task 2: Add The Seller Landing Page CSS Module

**Files:**
- Create: `frontend/src/app/sell/page.module.css`

- [ ] **Step 1: Add the CSS module**

Create `frontend/src/app/sell/page.module.css` with this content:

```css
.hero {
  background:
    linear-gradient(135deg, hsla(24, 100%, 96%, 0.95), hsla(152, 76%, 96%, 0.9)),
    var(--color-neutral-0);
  padding: var(--space-12) var(--space-4) var(--space-16);
}

.heroInner {
  max-width: var(--container-xl);
  margin-inline: auto;
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-10);
  align-items: center;
}

.heroCopy {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-5);
}

.eyebrow,
.sectionKicker {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  border: 1px solid var(--color-primary-200);
  border-radius: var(--radius-full);
  background: var(--color-primary-50);
  color: var(--color-primary-700);
  font-size: var(--font-xs);
  font-weight: var(--weight-semibold);
  letter-spacing: var(--tracking-wide);
  line-height: 1;
  padding: var(--space-2) var(--space-3);
  text-transform: uppercase;
}

.sectionKicker {
  background: var(--color-accent-50);
  border-color: var(--color-accent-200);
  color: var(--color-accent-700);
}

.heroTitle {
  max-width: 760px;
  font-size: clamp(2.5rem, 8vw, 4.5rem);
  line-height: 0.98;
  letter-spacing: var(--tracking-tight);
}

.heroDescription {
  max-width: 620px;
  color: var(--color-neutral-700);
  font-size: var(--font-lg);
}

.reviewNote {
  max-width: 600px;
  border-left: 4px solid var(--color-accent-500);
  color: var(--color-neutral-600);
  font-size: var(--font-sm);
  padding-left: var(--space-4);
}

.heroActions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.storefrontVisual {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--color-neutral-100);
  border-radius: var(--radius-xl);
  background: var(--color-neutral-0);
  box-shadow: var(--shadow-xl);
  min-height: 380px;
  padding: var(--space-5);
}

.awning {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  overflow: hidden;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  height: 54px;
  margin-bottom: var(--space-5);
}

.awning span:nth-child(odd) {
  background: var(--color-primary-500);
}

.awning span:nth-child(even) {
  background: var(--color-primary-100);
}

.shopSign {
  border: 1px solid var(--color-neutral-100);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  color: var(--color-neutral-0);
  font-size: var(--font-lg);
  font-weight: var(--weight-bold);
  margin-bottom: var(--space-5);
  padding: var(--space-4);
  text-align: center;
}

.shelves {
  display: grid;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.shelfRow {
  display: grid;
  grid-template-columns: 1fr 0.8fr 0.7fr;
  gap: var(--space-3);
  align-items: end;
  border-bottom: 6px solid var(--color-neutral-200);
  padding-inline: var(--space-2);
  padding-bottom: var(--space-2);
}

.productBox,
.productJar,
.productBoxSmall {
  display: block;
  border-radius: var(--radius-md) var(--radius-md) var(--radius-sm) var(--radius-sm);
}

.productBox {
  height: 76px;
  background: linear-gradient(160deg, var(--color-accent-400), var(--color-accent-700));
}

.productJar {
  height: 92px;
  border-radius: var(--radius-full) var(--radius-full) var(--radius-md) var(--radius-md);
  background: linear-gradient(160deg, var(--color-primary-200), var(--color-primary-500));
}

.productBoxSmall {
  height: 58px;
  background: linear-gradient(160deg, var(--color-warning), var(--color-primary-600));
}

.counter {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  border: 1px solid var(--color-accent-200);
  border-radius: var(--radius-lg);
  background: var(--color-accent-50);
  color: var(--color-neutral-900);
  padding: var(--space-4);
}

.counterLabel {
  display: block;
  color: var(--color-accent-700);
  font-size: var(--font-xs);
  font-weight: var(--weight-semibold);
  text-transform: uppercase;
}

.orderBadge {
  flex-shrink: 0;
  border-radius: var(--radius-full);
  background: var(--color-accent-600);
  color: var(--color-neutral-0);
  font-size: var(--font-xs);
  font-weight: var(--weight-bold);
  padding: var(--space-2) var(--space-3);
}

.sectionInner,
.dashboardInner,
.prepInner,
.finalCtaInner {
  max-width: var(--container-xl);
  margin-inline: auto;
}

.valueSection,
.processSection,
.categoriesSection,
.dashboardSection,
.prepSection,
.faqSection,
.finalCta {
  padding: var(--space-16) var(--space-4);
}

.valueSection,
.categoriesSection,
.faqSection {
  background: var(--color-neutral-0);
}

.processSection,
.prepSection {
  background: var(--color-neutral-50);
}

.sectionHeader {
  display: grid;
  gap: var(--space-3);
  max-width: 760px;
  margin-bottom: var(--space-10);
}

.sectionHeader h2,
.dashboardCopy h2,
.prepInner h2,
.finalCta h2 {
  font-size: clamp(2rem, 6vw, 3.25rem);
  letter-spacing: var(--tracking-tight);
}

.sectionHeader p,
.dashboardCopy p,
.prepInner p,
.finalCta p {
  color: var(--color-neutral-600);
  font-size: var(--font-lg);
}

.valueGrid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-4);
}

.valueCard,
.stepCard,
.categoryCard,
.faqItem {
  border: 1px solid var(--color-neutral-100);
  border-radius: var(--radius-md);
  background: var(--color-neutral-0);
  padding: var(--space-6);
}

.valueCard span {
  display: inline-flex;
  color: var(--color-primary-600);
  font-size: var(--font-xs);
  font-weight: var(--weight-bold);
  letter-spacing: var(--tracking-wide);
  margin-bottom: var(--space-4);
  text-transform: uppercase;
}

.valueCard h3,
.stepCard h3,
.categoryCard h3,
.faqItem h3 {
  font-size: var(--font-xl);
  margin-bottom: var(--space-3);
}

.valueCard p,
.stepCard p,
.categoryCard p,
.faqItem p {
  color: var(--color-neutral-600);
  font-size: var(--font-sm);
}

.stepsGrid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-4);
}

.stepCard {
  position: relative;
  min-height: 220px;
}

.stepNumber {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  background: var(--gradient-primary);
  color: var(--color-neutral-0);
  font-weight: var(--weight-bold);
  margin-bottom: var(--space-5);
}

.categoryGrid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-4);
}

.categoryIcon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  background: var(--color-accent-50);
  color: var(--color-accent-700);
  font-size: var(--font-sm);
  font-weight: var(--weight-bold);
  margin-bottom: var(--space-4);
}

.dashboardSection {
  background: var(--color-neutral-900);
  color: var(--color-neutral-0);
}

.dashboardInner {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-8);
  align-items: center;
}

.dashboardCopy {
  display: grid;
  gap: var(--space-4);
}

.dashboardCopy h2,
.dashboardCopy p {
  color: var(--color-neutral-0);
}

.dashboardCopy p {
  color: var(--color-neutral-300);
}

.featureList {
  display: grid;
  gap: var(--space-3);
  color: var(--color-neutral-200);
}

.featureList li {
  position: relative;
  padding-left: var(--space-6);
}

.featureList li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.65em;
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--color-accent-400);
}

.dashboardMockup {
  border: 1px solid hsla(0, 0%, 100%, 0.12);
  border-radius: var(--radius-xl);
  background: var(--color-neutral-0);
  color: var(--color-neutral-900);
  box-shadow: var(--shadow-2xl);
  overflow: hidden;
}

.mockupTopbar {
  display: flex;
  gap: var(--space-2);
  border-bottom: 1px solid var(--color-neutral-100);
  background: var(--color-neutral-50);
  padding: var(--space-4);
}

.mockupTopbar span {
  width: 10px;
  height: 10px;
  border-radius: var(--radius-full);
  background: var(--color-neutral-300);
}

.mockupStats {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-3);
  padding: var(--space-5);
}

.mockupStats div {
  border: 1px solid var(--color-neutral-100);
  border-radius: var(--radius-md);
  padding: var(--space-4);
}

.mockupStats span,
.inventoryRow span {
  display: block;
  color: var(--color-neutral-500);
  font-size: var(--font-xs);
  font-weight: var(--weight-semibold);
  text-transform: uppercase;
}

.mockupStats strong {
  display: block;
  font-size: var(--font-2xl);
  margin-top: var(--space-2);
}

.inventoryTable {
  display: grid;
  gap: var(--space-3);
  padding: 0 var(--space-5) var(--space-5);
}

.inventoryRow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  border: 1px solid var(--color-neutral-100);
  border-radius: var(--radius-md);
  padding: var(--space-4);
}

.inventoryRow strong {
  color: var(--color-accent-700);
  font-size: var(--font-sm);
}

.prepInner {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-8);
  align-items: start;
}

.prepInner > div {
  display: grid;
  gap: var(--space-3);
}

.checklist {
  display: grid;
  gap: var(--space-3);
}

.checklist li {
  position: relative;
  border: 1px solid var(--color-neutral-100);
  border-radius: var(--radius-md);
  background: var(--color-neutral-0);
  color: var(--color-neutral-800);
  font-weight: var(--weight-medium);
  padding: var(--space-4) var(--space-4) var(--space-4) var(--space-10);
}

.checklist li::before {
  content: "";
  position: absolute;
  left: var(--space-4);
  top: 50%;
  width: 10px;
  height: 10px;
  border-radius: var(--radius-full);
  background: var(--color-accent-500);
  transform: translateY(-50%);
}

.faqList {
  display: grid;
  gap: var(--space-3);
}

.faqItem {
  display: grid;
  gap: var(--space-2);
}

.faqItem h3 {
  margin-bottom: 0;
}

.finalCta {
  background:
    linear-gradient(135deg, hsla(24, 95%, 53%, 0.12), hsla(152, 68%, 38%, 0.12)),
    var(--color-neutral-0);
}

.finalCtaInner {
  display: grid;
  justify-items: start;
  gap: var(--space-4);
  border: 1px solid var(--color-neutral-100);
  border-radius: var(--radius-xl);
  background: var(--color-neutral-0);
  box-shadow: var(--shadow-lg);
  padding: var(--space-8);
}

@media (min-width: 640px) {
  .valueGrid,
  .categoryGrid,
  .mockupStats {
    grid-template-columns: repeat(2, 1fr);
  }

  .stepsGrid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 768px) {
  .hero {
    padding-block: var(--space-20);
  }

  .heroInner,
  .dashboardInner,
  .prepInner {
    grid-template-columns: 1.05fr 0.95fr;
  }

  .finalCtaInner {
    padding: var(--space-12);
  }
}

@media (min-width: 1024px) {
  .valueGrid,
  .categoryGrid {
    grid-template-columns: repeat(4, 1fr);
  }

  .stepsGrid {
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (max-width: 420px) {
  .heroActions {
    width: 100%;
  }

  .heroActions a,
  .finalCtaInner a {
    width: 100%;
  }

  .counter {
    align-items: flex-start;
    flex-direction: column;
  }
}
```

- [ ] **Step 2: Run lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: PASS.

- [ ] **Step 3: Commit Tasks 1 and 2 together**

Run:

```bash
git add frontend/src/app/sell/page.tsx frontend/src/app/sell/page.module.css
git commit -m "feat: add seller landing page"
```

Expected: commit succeeds.

## Task 3: Add Public Entry Points

**Files:**
- Modify: `frontend/src/components/Navbar.tsx`
- Modify: `frontend/src/components/Footer.tsx`
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Update navbar links**

In `frontend/src/components/Navbar.tsx`, find this block:

```tsx
  if (role === "customer" || role === "seller" || role === "admin") {
    navLinks.push({ href: "/stores", label: "Stores", icon: "🏪" });
  }
  if (role === "seller") {
    navLinks.push({ href: "/seller", label: "Seller", icon: "📊" });
  }
  if (role === "admin") {
    navLinks.push({ href: "/admin", label: "Admin", icon: "⚙️" });
  }
```

Replace it with:

```tsx
  if (!role || role === "customer") {
    navLinks.push({ href: "/sell", label: "Sell", icon: "🏪" });
  }
  if (role === "customer" || role === "seller" || role === "admin") {
    navLinks.push({ href: "/stores", label: "Stores", icon: "🏪" });
  }
  if (role === "seller") {
    navLinks.push({ href: "/seller", label: "Seller", icon: "📊" });
  }
  if (role === "admin") {
    navLinks.push({ href: "/admin", label: "Admin", icon: "⚙️" });
  }
```

- [ ] **Step 2: Update homepage secondary CTA**

In `frontend/src/app/page.tsx`, find this link:

```tsx
            <Link href={dbUser ? "/stores" : "/login"} className="btn btn-outline" id="cta-become-seller">
              Browse Stores
            </Link>
```

Replace it with:

```tsx
            <Link href="/sell" className="btn btn-outline" id="cta-become-seller">
              Sell on Khana Bazaar
            </Link>
```

- [ ] **Step 3: Update footer seller link**

In `frontend/src/components/Footer.tsx`, find:

```tsx
          <span className={styles.footerLink}>For Sellers</span>
```

Replace it with:

```tsx
          <Link href="/sell" className={styles.footerLink}>
            For Sellers
          </Link>
```

- [ ] **Step 4: Run lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add frontend/src/components/Navbar.tsx frontend/src/components/Footer.tsx frontend/src/app/page.tsx
git commit -m "feat: link seller landing page"
```

Expected: commit succeeds.

## Task 4: Production Build And Manual Verification

**Files:**
- No file changes expected.

- [ ] **Step 1: Run the production build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS and `/sell` appears in the built route output.

- [ ] **Step 2: Start the development server**

Run:

```bash
cd frontend && npm run dev
```

Expected: Next.js starts on `http://localhost:3000` unless that port is already taken.

- [ ] **Step 3: Manual browser checks**

Check these URLs and behaviors:

- `http://localhost:3000/sell`
  - The hero appears without horizontal scroll.
  - `Apply to sell` links to `/seller/signup`.
  - `See how it works` scrolls to the process section.
  - Value cards, process steps, category cards, dashboard preview, checklist, FAQ, and final CTA are visible.
- `http://localhost:3000/`
  - The secondary hero CTA reads `Sell on Khana Bazaar`.
  - The secondary hero CTA links to `/sell`.
- Navbar while logged out:
  - `Sell` appears.
  - `Sell` links to `/sell`.
- Footer:
  - `For Sellers` links to `/sell`.

- [ ] **Step 4: Stop the development server**

Stop the dev server with `Ctrl+C`.

- [ ] **Step 5: Record verification results**

Add the verification results to the final response:

```text
npm run lint: PASS
npm run build: PASS
Manual /sell check: PASS
```

If a command fails, include the failing command and the first actionable error in the final response.

## Self-Review Checklist

- The plan implements every design-spec requirement:
  - `/sell` route
  - Public static page
  - CTAs to `/seller/signup`
  - Anchor link to `#how-it-works`
  - Value cards without unsupported numeric claims
  - Four-step approval process
  - Store categories
  - Dashboard preview
  - Document checklist
  - FAQ
  - Final CTA
  - Navbar, homepage, and footer entry points
- No backend, auth, seller signup, OTP, or approval behavior changes are included.
- The plan uses existing Next.js App Router, CSS Modules, and design tokens.
- Verification uses the existing frontend scripts: `npm run lint` and `npm run build`.
