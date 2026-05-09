<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Chapter 3 — Google Maps API keys (optional)

*Teammate Guide > Chapter 3: Google Maps API keys (optional)*

> **Estimated time: about 30 minutes the first time.**

> **Skip this chapter if you only want the core e-commerce demo.** The app works without maps — addresses fall back to manual entry, store distances are not shown. Come back here when you want maps. Forward link: [Chapter 4 — Run the app for the first time](./04-first-run.md).

## What you are about to do

Google Maps is not free in production, but Google gives a generous monthly free tier that the demo will not come close to touching. You need to provide a payment method to unlock the APIs, but you will not be charged unless your usage goes far beyond anything a local dev environment produces.

Here is what you will do: create a Google Cloud account, link a payment method, enable three APIs, create two locked-down keys (one for the server, one for the browser), and paste each key into the right *[environment variable](./appendix-glossary.md#environment-variable)* file. From that point on, address autocomplete, the embedded map, and reverse geocoding all work in the app.

---

## 1. Sign in to Google Cloud

**Click in: web browser** — open `https://console.cloud.google.com`. Sign in with any Google account. If this is your first time, accept the terms of service.

---

## 2. Create the project

**Click in: web browser** — in the Google Cloud Console, click the project picker in the top bar (it usually shows "Select a project" or the name of a previous project). Click **New Project**.

- **Project name:** `khana-bazaar-maps`
- Leave the organization field as-is.
- Click **Create**.

Wait for the green check notification in the top-right corner (this takes about 10–20 seconds). After it appears, click the project picker again and make sure `khana-bazaar-maps` is the selected project. All the steps below depend on this.

[Screenshot: Google Cloud Console new-project dialog with name field]

---

## 3. Enable billing

**Click in: web browser** — open the hamburger menu (the three-line icon in the top-left corner) → **Billing** → **Link a billing account** → **Create billing account**. Follow the prompts.

> **Indian payment notes:**
>
> - **RuPay-only cards may be rejected** — use a Visa or Mastercard credit or debit card.
> - UPI is sometimes supported but not always available.
> - A free $300 trial credit may appear during setup; accept it if offered.

Google Maps Platform also gives **$200 of free Maps usage every month**, separate from any trial credit. The demo will not come close to using that amount. The billing account is required to unlock the APIs, not because Google expects to charge you.

---

## 4. Set a budget alert

**Click in: web browser** — go to **Billing** → **Budgets & alerts** → **Create Budget**.

- **Name:** `khana-bazaar dev safety net`
- **Amount:** `$5` per month
- Set email alerts at **50%**, **90%**, and **100%**.
- Click **Finish**.

This is a paranoia floor, not the real free-tier ceiling. You will receive an email warning long before any real charge could occur. If you ever see one of these alerts, stop and investigate before continuing.

---

## 5. Enable the three APIs

**Click in: web browser** — go to **APIs & Services** → **Library**.

Search for and enable each of the following three APIs, one at a time. Click the API name in the search results, then click the blue **Enable** button.

1. **Maps JavaScript API** — renders the embedded map inside the address picker.
2. **Places API** — powers the address autocomplete suggestions as you type. Search for exactly "Places API" in the library; the result you want shows "Places API" without any qualifier in the title.
3. **Geocoding API** — converts a typed address into latitude and longitude (and back when you drag the map pin).

Do **not** enable other Maps APIs such as Routes, Roads, or Air Quality. They bill separately and the app does not use them.

[Screenshot: API Library showing Maps JavaScript API "Enable" button]

---

## 6. Create the server key

**Click in: web browser** — go to **APIs & Services** → **Credentials** → **+ Create credentials** → **API key**.

The key appears in a modal. Copy it somewhere temporary, then click **Edit API key** (the pencil icon next to the new key in the credentials list).

Set the following:

- **Name:** `khana-bazaar-server`
- **API restrictions** → **Restrict key** → tick **Places API** and **Geocoding API** only. Untick everything else — in particular, do not tick Maps JavaScript API. The server never renders maps; it only does autocomplete lookups and geocoding.
- **Application restrictions** → leave at **None**.

Leaving Application restrictions at None means the key is not locked to a specific IP address. Home internet IP addresses change when your Wi-Fi reconnects, so locking the key to one IP causes the app to break unpredictably. Locking to a static IP is a production concern, not a local-dev concern. For a deeper discussion, see the engineer doc `../google_maps_setup.md` §12.

Click **Save**.

[Screenshot: Edit API key form, API restrictions section, Places + Geocoding ticked]

**If it fails.** [./06-troubleshooting.md#request-denied](./06-troubleshooting.md#request-denied)

---

## 7. Create the browser key

**Click in: web browser** — go to **APIs & Services** → **Credentials** → **+ Create credentials** → **API key**. Edit the new key.

Set the following:

- **Name:** `khana-bazaar-browser`
- **API restrictions** → **Restrict key** → tick **only** Maps JavaScript API. Untick Places API and Geocoding API — the browser never calls those directly. Those calls go through the *[backend](./appendix-glossary.md#backend)*, which uses the server key.
- **Application restrictions** → **HTTP referrers** → click **Add an item** and add each of the following, exactly as written (the trailing `/*` is required):
  - `http://localhost:3000/*`
  - `http://127.0.0.1:3000/*`

Click **Save**.

**If it fails.** [./06-troubleshooting.md#referrer-not-allowed](./06-troubleshooting.md#referrer-not-allowed)

---

## 8. Paste the keys into your env files

**Run in: WSL2 Ubuntu terminal**

Open the backend *[environment variable](./appendix-glossary.md#environment-variable)* file:

```bash
nano backend/app/.env
```

Find the line:

```
GOOGLE_MAPS_SERVER_API_KEY=""
```

Replace the empty string with your server key:

```
GOOGLE_MAPS_SERVER_API_KEY="<your-server-key>"
```

Save and exit: press **Ctrl+O**, then **Enter**, then **Ctrl+X** (same as chapter 2).

Now open the *[frontend](./appendix-glossary.md#frontend)* env file:

```bash
nano frontend/.env.local
```

Find the line:

```
NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=""
```

Replace it with your browser key:

```
NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY="<your-browser-key>"
```

Save and exit.

*Leave the backend's `GOOGLE_MAPS_BROWSER_API_KEY` line empty — it is not read at runtime.*

If the app is already running, restart it so the backend re-reads the env file:

```bash
./scripts/dev.sh restart
```

Skip this restart if you have not started the app yet — chapter 4 will do the first start.

---

## 9. Test it works

These checks assume the app is running (see chapter 4 if it is not).

**Check 1 — Autocomplete**

**Click in: web browser** — open `http://localhost:3000`. Click **Set location** (or your saved address if you've set one) in the navbar. Type `andheri`. You should see Indian address autocomplete suggestions appear in a dropdown.

**If it fails.** [./06-troubleshooting.md#request-denied](./06-troubleshooting.md#request-denied)

**Check 2 — Embedded map**

Scroll down inside the address picker. You should see an embedded map showing the Mumbai area.

If the map shows a gray tile with "For development purposes only" watermark text, the browser key is not being picked up.

**If it fails.** [./06-troubleshooting.md#dev-watermark](./06-troubleshooting.md#dev-watermark)

**Check 3 — Reverse geocoding**

Drag the pin on the map to a new location. The city, state, and pincode fields below the map should fill in automatically.

---

## When something goes wrong

- Autocomplete returns errors or no results → [./06-troubleshooting.md#request-denied](./06-troubleshooting.md#request-denied)
- Browser key blocked by referrer check → [./06-troubleshooting.md#referrer-not-allowed](./06-troubleshooting.md#referrer-not-allowed)
- Map shows "For development purposes only" watermark → [./06-troubleshooting.md#dev-watermark](./06-troubleshooting.md#dev-watermark)

For deeper detail on cost orientation, key rotation, and the local-dev shortcut, see the engineer doc: [`../google_maps_setup.md`](../google_maps_setup.md) (§10 cost orientation, §11 key rotation, §12 local-dev shortcut).

---

← [Previous: Chapter 2 — Get the code and configure secrets](./02-clone-and-env.md)  |  Next: [Chapter 4 — Run the app for the first time](./04-first-run.md) →
