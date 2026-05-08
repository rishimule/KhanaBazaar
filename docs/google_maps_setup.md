# Google Maps API Keys — Setup Guide

How to provision the two Google Maps API keys Khana Bazaar needs for address autocomplete, the map pin picker, and reverse geocoding. The keys are restricted in two different ways so they cannot be abused if leaked. Plan ~20 minutes the first time, ~5 minutes thereafter.

## 0. What you'll have at the end

| Key | Purpose | Restriction | Goes into |
|---|---|---|---|
| **Server key** | Backend proxy calls (Places Autocomplete, Place Details, Reverse Geocoding) | **API restriction** to those three APIs + **IP restriction** to your backend's outbound IPs | `GOOGLE_MAPS_SERVER_API_KEY` (backend `.env`) |
| **Browser key** | Renders the embedded map in `<MapPicker>` | **API restriction** to Maps JavaScript API + **HTTP-referrer restriction** to your frontend domain(s) | `GOOGLE_MAPS_BROWSER_API_KEY` and `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY` (frontend `.env.local`) |

You should never have one key with no restrictions.

## 1. Prerequisites

- A Google account.
- A credit card (Google requires one even for the free tier; you will only be charged if you exceed the monthly $200 credit).
- ~20 minutes the first time.

## 2. Create or reuse a GCP project

1. Open the Google Cloud Console — https://console.cloud.google.com.
2. Top-bar project picker → **New Project**.
3. Name it `khana-bazaar-maps` (or reuse an existing project — fine, but the keys + billing live in whatever project you pick).
4. Click **Create**, wait for the green check, then make sure the project is selected in the picker.

## 3. Enable billing

Maps Platform requires a billing account. Without it, every API call returns `REQUEST_DENIED` and the backend logs `geo provider not configured`-class errors.

1. Hamburger menu → **Billing**.
2. **Link a billing account** → either pick an existing one or create one (`Add billing account` → enter card details).
3. Confirm the billing account is **Active** for the project.

> **Cost orientation.** Google gives **$200/month free Maps Platform credit**. At Khana Bazaar's MVP scale that covers thousands of session-based autocomplete + place-details flows. You'll typically exceed the free tier only after a few thousand DAU. See §10 below for the line-item costs.

## 4. Enable the three APIs

You need exactly three APIs enabled — no more.

1. Hamburger menu → **APIs & Services** → **Library**.
2. Search and enable each of:
   - **Places API** (powers `/api/v1/geo/autocomplete` + `/api/v1/geo/place/{id}`)
   - **Geocoding API** (powers `/api/v1/geo/reverse` + the seller-address backfill task)
   - **Maps JavaScript API** (powers the embedded `<MapPicker>` map render)
3. After each, click **Enable** and wait for the page to confirm.

Do not enable any other Maps APIs (Routes, Roads, Air Quality, etc.) — they're billed separately and we don't use them.

## 5. Create the SERVER key

This is the powerful key. It must never reach the browser.

1. **APIs & Services** → **Credentials** → **+ Create credentials** → **API key**.
2. The key appears in a modal — copy it; you'll restrict it before it can be used.
3. Click **Edit API key** (pencil icon) on the new entry.
4. **Name**: `khana-bazaar-server`.
5. **API restrictions** → **Restrict key** → tick:
   - Places API
   - Geocoding API

   Untick everything else, including Maps JavaScript API. The server never renders maps.
6. **Application restrictions** → **IP addresses** → add the public IPs that your backend will call Google from:

   - **Local dev**: leave restriction at **None** for now (your laptop's IP changes). Tighten before you go to prod.
   - **Production on Azure Container Apps**: add the Container App Environment's static outbound IPs. Find them with:
     ```bash
     az containerapp env show \
        --name kb-prod-cae-cin --resource-group kb-prod-rg \
        --query 'properties.staticIp' -o tsv
     ```
     Add that as a single IP (no CIDR mask needed). If you scale into multiple regions, repeat for each.
   - **Self-hosted / VPS**: add the box's public IPv4.

7. **Save**.

> Why IP-restrict and not referrer-restrict? Backend traffic has no `Referer` header. The `Referer` restriction is for browser keys only.

## 6. Create the BROWSER key

This key is shipped to every visitor's browser. The referrer restriction is what stops it from being scraped and reused on someone else's site.

1. **APIs & Services** → **Credentials** → **+ Create credentials** → **API key**.
2. **Edit API key** on the new entry.
3. **Name**: `khana-bazaar-browser`.
4. **API restrictions** → **Restrict key** → tick **only**:
   - Maps JavaScript API

   Untick Places API and Geocoding API. The browser never calls those directly.
5. **Application restrictions** → **HTTP referrers (web sites)** → add each origin where the bundle is served:
   - **Local dev (Next.js)**: `http://localhost:3000/*`
   - **Local dev (mobile via ngrok)**: `https://*.ngrok-free.app/*` (ngrok hostname rotates)
   - **Production**: `https://www.khanabazaar.in/*` and `https://khanabazaar.in/*`

   The trailing `/*` is required. Save each entry one at a time.
6. **Save**.

> Why is referrer-restriction enough? If a leaked key is used from another origin, Google's edge rejects the request before the call hits Maps Platform. There is no separate IP allowlist for browser keys.

## 7. Wire the keys into Khana Bazaar

### Backend (`backend/app/.env`)

```dotenv
# Server key — IP-restricted in GCP. Never returned to the browser.
GOOGLE_MAPS_SERVER_API_KEY="AIzaSy...your-server-key..."

# Tunables (defaults shown; raise GEO_RATE_LIMIT_PER_MIN if you front many users behind one NAT)
GEO_RATE_LIMIT_PER_MIN=30
GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS=60
GEO_REVERSE_CACHE_TTL_SECONDS=86400
```

Restart the API + Celery worker after editing. The server key is also used by the one-shot `geo.backfill_store_addresses` Celery task.

### Frontend (`frontend/.env.local`)

```dotenv
# Browser key — referrer-restricted in GCP. Inlined into the JS bundle at build time.
NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY="AIzaSy...your-browser-key..."
```

`NEXT_PUBLIC_*` is baked in by `next build`. Change the key → rebuild the bundle (`npm run build`) → restart `npm run dev`.

### Production (Azure)

See `azure_deployment.md` §7.7 — both keys land in Azure Key Vault as `google-maps-server-api-key` and `google-maps-browser-api-key`. The browser key is passed to the web Container App as a build-time env var; the server key is mounted on the API + worker Container Apps via `secretRef`.

## 8. Verify it works

Take ~3 minutes. With both backend (`uv run uvicorn app.main:app --reload`) and frontend (`npm run dev`) running:

1. **Autocomplete** — open http://localhost:3000, click the navbar **Set location** chip, type `andheri`. You should see Indian autocomplete suggestions in the dropdown.
   - If you see "Suggestions unavailable, type address manually": check the API server logs. Most common: `REQUEST_DENIED` (key not restricted to Places API), `OVER_QUERY_LIMIT` (billing not active).
2. **Map render** — in the same picker, scroll down to the map. You should see a Google map centered on Mumbai with a red pin.
   - If the map is gray with "For development purposes only": the browser key isn't restricted correctly OR billing isn't enabled.
3. **Reverse geocode** — drag the pin. The picker should fill in city/state/pincode.
4. **Serviceability** — log in as a customer, add an address with the pin, then open a store's checkout page. The address dropdown should show the address as enabled (or disabled if the store's `delivery_radius_km` doesn't cover it).

Backend smoke test (no FE required):

```bash
# Replace SERVER_KEY and confirm IP allowlist includes your dev box.
curl "http://localhost:8000/api/v1/geo/autocomplete?q=mumbai&session_token=test123"
```

Expected: `{"predictions":[{"place_id":"...","description":"Mumbai, Maharashtra, India"}, ...]}`.

## 9. Common errors

| Symptom | Likely cause | Fix |
|---|---|---|
| `geo provider not configured` (503 from `/geo/*`) | `GOOGLE_MAPS_SERVER_API_KEY` empty | Set the env var, restart the API |
| `REQUEST_DENIED` in logs | Server key missing API restriction OR IP restriction blocked the call OR billing not enabled | Check **Credentials** → server key → API restrictions includes Places + Geocoding. Verify billing is **Active**. |
| Browser map gray with "For development purposes only" watermark | Browser key missing API restriction or referrer-restricted to wrong origin OR billing not enabled | Edit the browser key → ensure **Maps JavaScript API** is selected and your origin is in the HTTP-referrer list. |
| `OVER_QUERY_LIMIT` | You've blown the daily quota (free tier is well above MVP needs) | Tighten cache TTLs (`GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS`, `GEO_REVERSE_CACHE_TTL_SECONDS`); investigate runaway autocomplete on the FE; raise the quota cap in GCP if legitimate |
| Autocomplete returns city/country results from outside India | The `components=country:in` filter is set in `core/google_maps.py`; if you removed it, Indian-only is no longer enforced | Don't remove the filter — KhanaBazaar is India-only |
| The pin loads but reverse-geocode fails on every drag | Geocoding API not enabled OR not on the server key's restricted-API list | Re-check `APIs & Services → Library → Geocoding API` is enabled and the server key has it ticked |
| 429 from `/api/v1/geo/*` for legitimate users | Per-IP rate limit exceeded (default 30/min) — typical when many users sit behind one NAT | Bump `GEO_RATE_LIMIT_PER_MIN` in backend `.env` (and Key Vault in prod) |

## 10. Cost & quota orientation

Pricing as of 2026 (always check the [official price sheet](https://mapsplatform.google.com/pricing/) — Google has rebranded SKUs before).

| SKU | Per-call price | What we use it for |
|---|---|---|
| **Places Autocomplete – Per Session** | $2.83 / 1,000 sessions | Each address-entry session in the FE (one autocomplete + one place-details fetch counts as one session, billed at the place-details call) |
| **Geocoding** | $5 / 1,000 requests | Reverse geocode after pin drop, plus the seller backfill |
| **Maps JavaScript API – Dynamic Maps load** | $7 / 1,000 loads | One charge per `<MapPicker>` render |

Free tier ($200/month credit) covers roughly:

- ~70k autocomplete sessions, OR
- ~40k reverse geocodes, OR
- ~28k map loads

In practice the Redis cache (60s on autocomplete, 24h on reverse geocode) keeps repeat traffic off Google. Most pages also reuse the same map render.

### Set hard quota caps in GCP

Belt-and-braces against runaway scripts:

1. **APIs & Services** → **Quotas**.
2. Filter by each API (Places, Geocoding, Maps JavaScript).
3. Edit each per-day quota down to a sane ceiling (e.g. 5,000/day) until you have organic traffic. Raise as you grow.

## 11. Key rotation

Rotate either key any time the value may have leaked (committed to a repo, screenshot, etc.).

1. Create a **new** key with the same restrictions in GCP.
2. Update the env var in `.env` (dev) or Key Vault (prod) and restart.
3. Watch the API and FE logs for ~30 minutes — confirm no requests use the old key.
4. **Delete** the old key entirely (do not just disable; deletion is irreversible and easier to reason about).

For the browser key specifically: because it's inlined into the JS bundle, every visitor caching the old bundle still uses the old key until they re-download. Either bust the CDN cache or expect a 1–2 day overlap window where both keys must remain valid. If the browser key was leaked publicly, force-bust the CDN immediately.

## 12. Local dev shortcut

If you don't want to provision real keys for local dev, leave both env vars empty:

- Backend: `GOOGLE_MAPS_SERVER_API_KEY=""` → `/api/v1/geo/*` returns `503 geo provider not configured` → frontend autocomplete + reverse fall back to "type manually" mode.
- Frontend: `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=""` → `<MapPicker>` shows the fallback "Map unavailable" panel.

The rest of the app keeps working: address forms accept manual input, addresses save without lat/lng (so DIGIPIN stays null + `geo` stays NULL + the address won't appear in distance-sorted store lists). Useful for unit-testing UI flows that don't touch geo.
