<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Appendix — How nearby stores are picked for price comparison

*Teammate Guide > Appendix: How nearby stores are picked for price comparison*

> Estimated reading time: about 8 minutes.

---

## What this feature is

On the checkout page (`/checkout/<storeId>/<serviceId>`), a customer can open a panel called **"Compare prices at nearby stores"**. The app suggests up to **two** other shops nearby that sell the same kind of goods (groceries, food, pharmacy, etc.) and shows how much the same cart would cost there. The customer can then one-tap "Shop at <store>" to move their cart over without losing their original cart.

This appendix explains, in plain language, **how the app decides which two stores to suggest**.

---

## What has to be true before suggestions show up

The "Compare prices" toggle stays disabled until **all three** of these are true:

1. The customer is **logged in** (we need a customer profile to call the backend).
2. The customer has **picked a delivery address** (so we know their location).
3. The current store is **serviceable** for that address.

Without a delivery address, the backend has nothing to compare distance against, so we hide the option rather than guess.

---

## The 5 filters that narrow down candidates

Once the customer opens the panel, the backend looks at **every store in the system** and keeps only those that pass **all five** of the following filters:

| # | Filter | In plain English |
|---|---|---|
| 1 | **Active** | The shop is currently open for business on the platform (not paused, suspended, or deleted). |
| 2 | **Not the current store** | We never suggest the same shop the customer is already checking out at. |
| 3 | **Has a location** | The shop has a real address with map coordinates. Shops without coordinates can't be compared by distance. |
| 4 | **Delivers to the customer** | The customer's chosen delivery address falls inside the shop's delivery radius. Each shop sets its own radius (default 5 km). A shop that only delivers 3 km away is skipped if the customer is 4 km out. |
| 5 | **Sells the same service** | If the customer is checking out a **grocery** basket, only shops registered for the "grocery" service stay. A pure pharmacy will be ignored. The current cart's service decides this. |

Of every shop that passes these five filters, we keep the **20 nearest** ones. That's the "candidate pool".

---

## How the final 2 winners are chosen

The backend then does a quick calculation for each of those 20 candidates:

For each item in the customer's cart, it asks:

- **Does this candidate shop stock this item?** If yes, use that shop's price.
- **No?** Pretend the customer would still buy that one item from the original shop, at the original shop's current price. (This is called "imputing" the missing items.)

Add up everything → that's the candidate's **"end-to-end total"**.

Then we rank the 20 candidates by:

1. **Cheapest end-to-end total first** — the shop that would cost the customer the least money overall wins.
2. **Tie-breaker: closer to the customer** — if two shops would cost exactly the same, the nearer one wins.

We also **drop any shop that stocks zero items from the cart** — suggesting a shop that has nothing the customer wants is just noise.

Finally we keep the **top 2** of whatever's left. That's why the feature shows at most two alternatives, never three.

---

## A worked example

> Suppose the customer is shopping at **Akash Mart** for ₹450 of grocery items: 1 kg rice, 1 dozen eggs, 1 packet biscuits.
>
> The backend finds 20 nearby grocery shops within their delivery radius. After the five filters, two stand out:
>
> - **Sai Provisions** (1.2 km away) — stocks rice and eggs cheaper, but doesn't carry that biscuit brand. End-to-end total = ₹398 (₹350 at Sai + ₹48 imputed biscuit from Akash).
> - **Bharat Kirana** (1.8 km away) — stocks all three items. End-to-end total = ₹510.
>
> The app suggests Sai Provisions first (cheaper), then Bharat Kirana. The customer sees a green **"Save ₹52"** chip on the Sai card and a grey **"₹60 more"** chip on Bharat.

---

## Why a customer might see **no** suggestions

Even after enabling the toggle, the panel can come back empty. The most common reasons:

- **Rural / fringe address** — no other shops are within their delivery radius.
- **Specialty service** — the customer is buying from the only pharmacy serving their area.
- **Every nearby shop stocks none of the cart items** — every candidate got dropped by the "zero stock" rule.

In these cases the panel shows "No other stores in your area offer this service right now." Not a bug — just nothing better to suggest.

---

## Where the logic actually lives

| What | Where to look |
|---|---|
| The 5-filter SQL query + ranking | `backend/app/src/app/services/price_comparison.py` |
| The customer-facing panel | `frontend/src/components/orders/PriceComparison.tsx` |
| The desktop table + mobile card layout | `frontend/src/components/orders/PriceComparisonTable.tsx` |
| Switch-store dialog (one-tap rebuild) | `frontend/src/components/orders/SwitchStoreDialog.tsx` |
| Higher-level feature overview (for engineers) | `docs/price_comparison.md` |

Tunable constants live at the top of the backend service file:

- `MAX_ALTERNATIVES = 2` — change to suggest more (or fewer) shops.
- `CANDIDATE_POOL_LIMIT = 20` — change how many nearby shops are even considered.

---

## TL;DR

> *"The two nearest stores that deliver to the customer, sell the same kind of goods, stock at least one cart item, and would cost the least overall — cheapest first, nearest as the tie-breaker."*
