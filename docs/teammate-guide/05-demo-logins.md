# Chapter 5 — Demo accounts and login flow

*Teammate Guide > Chapter 5: Demo accounts and login flow*

> **Estimated time:** about 20 minutes for the demo script.

Now that the app is running, this chapter shows you how to log in as the three kinds of user, and walks through a 5-minute end-to-end demo.

---

## How OTP login works in dev {#otp-login-flow}

Type your email on the login screen and click **Send code** — the *[backend](./appendix-glossary.md#backend)* generates a 6-digit code and prints it to its log instead of sending a real email. Copy that code, paste it into the *[OTP](./appendix-glossary.md#otp)* input on the login screen, and click **Verify** — you are in. No real email is sent in dev.

---

## Where the OTP code appears {#read-otp-from-log}

**Click in: web browser** — open `http://localhost:8001`. **You should see** a log viewer with four tabs.

1. Click the **backend** tab.
2. After requesting an OTP on the storefront, look for a log line that contains the email address and a 6-digit number. Example shape:

   ```
   EMAIL to=customer@khanabazaar.dev code=123456
   ```

   [Screenshot: log viewer with backend tab and a 6-digit OTP line highlighted]

   Note: the exact log format may vary — the line always contains the email plus a 6-digit number.

3. Tip: use Ctrl+F in the log viewer to search by email address if the log is busy.

---

## Demo accounts {#demo-accounts}

*This list is sourced from `backend/app/src/app/db/dev_seed.py`. If new accounts are added there, update this table.*

| Role | Email | What they see / can do |
|---|---|---|
| Admin | `admin@khanabazaar.dev` | Approve seller applications, manage master catalogue (services, categories, products), see all orders and stores. |
| Customer | `customer@khanabazaar.dev` | Set delivery address, browse stores, add to cart, place orders, track orders. Logged in as Priya Verma. |
| Seller (approved, primary) | `seller@khanabazaar.dev` | Manage their own store inventory and prices, see incoming orders, mark orders packed/dispatched/delivered. |
| Seller (approved, others) | `seller2@khanabazaar.dev` … `seller9@khanabazaar.dev` | Same as above for eight other stores. Useful when demoing multiple sellers. |
| Seller application — pending | `pending.seller@khanabazaar.dev` | Brand-new application. Lands on the "awaiting approval" screen. Useful for the admin tour. |
| Seller application — approved record | `approved.seller@khanabazaar.dev` | Already-approved application record. Useful in admin's "approvals history". |
| Seller application — rejected record | `rejected.seller@khanabazaar.dev` | Rejected application record. Useful in admin's "approvals history". |

---

## First login walkthrough — customer {#customer-first-login}

1. **Click in: web browser** — open `http://localhost:3000`.
2. Click **Login** in the navbar. [Screenshot: storefront navbar with Login button highlighted]
3. Type `customer@khanabazaar.dev` and click **Send code**.
4. Switch to your log viewer tab (`http://localhost:8001`, **backend** tab).
5. Find the *[OTP](./appendix-glossary.md#otp)* line — copy the 6-digit code.
6. Switch back to the storefront tab. Paste the code into the OTP input.
7. Click **Verify**. You land on the storefront, logged in as Priya Verma.

---

## 5-minute demo script {#demo-script}

These three steps form a complete end-to-end walkthrough you can perform live for a stakeholder. Each step builds on the previous one — the order ID you generate in Step 1 shows up in the seller's dashboard in Step 2.

### Step 1 — As customer (~2 minutes)

1. Set a delivery address (skip this step if maps are not configured — chapter 3 was optional).
2. Open a store from the storefront list.
3. Add three items to the cart.
4. Open the cart drawer.
5. Click **Checkout**.
6. Place the order. **Note the order ID** — you will see this same order in the seller dashboard next.

### Step 2 — Switch to seller (~2 minutes)

1. Logout (top-right user menu).
2. Log in as `seller@khanabazaar.dev` using the same OTP-via-log dance (see [Where the OTP code appears](#read-otp-from-log)).
3. The seller dashboard shows the new order from Step 1.
4. Mark it: **Packed** → **Dispatched** → **Delivered**.

### Step 3 — Switch to admin (~1 minute)

1. Logout.
2. Log in as `admin@khanabazaar.dev`.
3. Open the **Catalog** tab — show the master products list.
4. Open the **Sellers** tab — show the pending application from `pending.seller@khanabazaar.dev`.
5. Click **Approve**. The seller becomes active.

---

## Page tour by role {#page-tour}

This section describes what you see when navigating each major area of the app as each primary role. Exact button labels may have shifted since this guide was written — read these descriptions for intent, not literal layout.

### Customer

**Home / store list.** The storefront landing page at `http://localhost:3000` shows a list of stores available near the selected delivery location. Each card displays the store name, the services it offers (Grocery, Food, Pharmacy, etc.), and distance from your address. Clicking a card opens the store detail view.

**Store detail (Instacart-style 3-pane layout).** The store detail page divides the screen into three vertical panels. The left panel lists the services available at that store. Clicking a service updates the middle panel, which shows the categories within that service. Clicking a category updates the right panel, which shows the products in that category at that store's prices and stock levels. From here you add items to the cart.

**Cart drawer.** A slide-out panel on the right side of the screen shows every item in the current store's cart, quantities, line-item prices, and a subtotal. You can increment or decrement quantities from here. The drawer has a **Checkout** button at the bottom that takes you to the per-store checkout page. Each store has its own independent cart — items from different stores are never mixed.

**Per-store checkout.** The checkout page collects the delivery address and confirms the payment method (UPI in production; in dev the flow completes without a real payment). After placing the order, you see a confirmation screen with the new order ID.

**Account — Addresses.** Under your account menu, the Addresses page lets you save, rename, and delete delivery addresses. Addresses are verified against the map — the system confirms the pin falls within a reachable delivery zone before saving.

**Account — Orders.** The Orders page lists every order you have placed, grouped by store. Clicking an order shows the items, the current status (pending, packed, dispatched, delivered), and the delivery address. The status updates in real time as the seller moves the order through its lifecycle.

**Account — Settings.** The Settings page lets you update your display name and contact preferences.

---

### Seller

**Dashboard.** The seller dashboard at `http://localhost:3000/seller` is the home screen after login. It shows a summary of recent orders and any alerts requiring action (low stock, new orders). From here you navigate to every other seller section.

**Services list.** The Services page shows which service types (Grocery, Food, Pharmacy, etc.) the store has activated. Each service maps to the master catalogue's service hierarchy. Sellers can enable or disable services to control which categories appear in their storefront.

**Inventory.** The Inventory page shows every product stocked in the store, with editable fields for price and quantity. Changes take effect immediately — the storefront reflects updated prices and stock levels on the next load. Inventory is per-product per-store, so each seller controls their own pricing independently of the master catalogue.

**Orders.** The Orders page lists all orders placed at this store, newest first. Clicking an order expands the items, delivery address, and customer contact. The seller moves each order through four statuses: **Pending** → **Packed** → **Dispatched** → **Delivered**. Clicking the status button advances it one step.

**Store profile.** The Store profile page lets the seller update their store name, description, contact details, delivery radius, and map pin. The map pin must be confirmed before the store appears in customer location searches.

---

### Admin

**Catalog — Services.** The top level of the master catalogue lists all service types (Grocery, Food, Pharmacy, etc.) in every supported language. Admins create and edit services here; translations for Hindi, Marathi, Gujarati, and Punjabi are managed from this screen alongside English.

**Catalog — Categories.** Under each service, categories organize products into logical groups (e.g., "Vegetables", "Dairy" under Grocery). Admins add, rename, and reorder categories. Category changes cascade to all stores — sellers see the updated hierarchy immediately.

**Catalog — Subcategories.** Subcategories sit below categories and provide finer-grained product grouping. The admin creates and labels subcategories; sellers then assign their stocked products to the matching subcategory.

**Catalog — Master products.** The master product list is the source of truth for product names, images, and descriptions across all stores. Sellers do not create new products — they pick from this master list and add their own price and stock count. Admins curate this list by adding new products, editing names or images, and retiring discontinued items.

**Sellers — Applications.** The Applications tab shows every seller who has submitted a registration form. Each row shows the applicant's business name, email, phone, and application date. Admins can review the details and click **Approve** or **Reject**. Approving immediately unlocks the seller's dashboard; rejecting prevents login and flags the record.

**Sellers — Approvals history.** A separate view shows all previously processed applications, filterable by status (approved or rejected). Useful for auditing past decisions or finding a seller who was rejected and has re-applied.

**Orders (all stores).** The admin orders view aggregates orders across every store on the platform. Admins can filter by store, status, or date range. This view is for oversight and dispute resolution — admins do not change order statuses here.

**Languages.** The Languages page lists the supported interface languages (currently English, Hindi, Marathi, Gujarati, Punjabi). Admins can add a new language, which immediately makes it available for translation entries in the catalogue.

---

*Exact button labels may have shifted since this guide was written — read these descriptions for intent, not literal layout.*

---

← [Previous: Chapter 4 — Run the app for the first time](./04-first-run.md)  |  Next: [Chapter 6 — When things break](./06-troubleshooting.md) →
