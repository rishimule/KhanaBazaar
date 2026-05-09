<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Mumbai-Anchored Seed Data — Design Spec

**Date:** 2026-05-08
**Status:** Draft — awaiting user review

## Goal

Replace the cross-India seed dataset with 9 real Mumbai store locations and 5 customer delivery addresses so a developer can manually exercise every geo-aware feature (distance sort, per-store delivery radius, serviceability gating, order 422 path) without provisioning extra data. Seed runs must stay offline-reproducible — Google Maps is hit only once, at authoring time, and the results are baked into the seed file.

## Decisions locked during brainstorming

| Topic | Decision |
|---|---|
| Store layout | 9 Mumbai stores spread across Bandra, Andheri, Colaba, Powai, Worli, Juhu, Dadar, Lower Parel, Goregaon |
| Delivery radii | Mixed 1 km – 15 km so a single customer address sees a serviceable / non-serviceable mix |
| Customer addresses | 5 on `customer@khanabazaar.dev`: Home (Bandra, default), Office (Lower Parel), Friend's (Andheri), Parents (Powai), Pune Trip (out-of-Mumbai) |
| lat/lng provenance | One-shot Google reverse-geocode at **bake** time, results hardcoded in `dev_seed.py`. Recurring seed runs never touch Google. |
| `pin_confirmed` for seeded stores | True (modeled as if seller pinned during signup) |
| `location_source` for seeded addresses | `pin` |
| DIGIPIN for seeded addresses | Auto-derived from lat/lng inside the seed-time `_upsert_address` helper |

## 1. Mumbai store dataset

Each entry replaces the corresponding row in the existing `STORES` list in `backend/app/src/app/db/dev_seed.py`. Seller mapping (`seller_idx`) and inventory linkage are preserved — only address + radius fields change, plus `place_id`, `location_source`, `delivery_radius_km`, `pin_confirmed` are added.

| seller_idx | Store name | Neighborhood | Approx lat / lng | radius_km |
|---|---|---|---|---|
| 1 | Sharma General Store | Bandra West (Linking Rd) | 19.060, 72.831 | 5.0 |
| 2 | Krishna Supermart | Andheri West (Lokhandwala) | 19.135, 72.829 | 3.0 |
| 3 | Balaji Fresh Market | Colaba (Causeway) | 18.910, 72.815 | 2.0 |
| 4 | Powai Pulse Pharmacy | Powai (Hiranandani) | 19.117, 72.910 | 8.0 |
| 5 | Worli Daily Needs | Worli (Sea Face) | 19.018, 72.815 | 5.0 |
| 6 | Juhu Beach Bites | Juhu (Tara Rd) | 19.099, 72.826 | 1.0 |
| 7 | Dadar Dawakhana | Dadar West (Kabutar Khana) | 19.018, 72.844 | 15.0 |
| 8 | Lower Parel Larder | Lower Parel (Kamala Mills) | 18.998, 72.829 | 4.0 |
| 9 | Goregaon Grocers | Goregaon East (Aarey Rd) | 19.165, 72.851 | 3.0 |

The lat/lng above are **author-time approximations**. The bake script (§3) replaces them with Google's canonical values plus `place_id` and `formatted_address`. The user-visible `address_line1` is taken from Google's `formatted_address` first segment; `city`, `state`, `pincode` come from the parsed components.

## 2. Customer delivery addresses

`customer@khanabazaar.dev` (`Priya Verma`) gets 5 addresses. Default = entry 1 (Bandra Home).

| # | Label | Neighborhood | Approx lat / lng | Coverage prediction |
|---|---|---|---|---|
| 1 | Home (default) | Bandra West (16th Rd) | 19.062, 72.835 | Serviceable: Sharma, Dadar. Edge: Andheri. Outside: 6 others. |
| 2 | Office | Lower Parel (Senapati Bapat Marg) | 19.001, 72.829 | Serviceable: Lower Parel, Worli, Dadar. Outside: rest. |
| 3 | Friend's Place | Andheri East (SEEPZ) | 19.122, 72.870 | Serviceable: Powai, Dadar. Outside: rest. |
| 4 | Parents | Powai (IIT Bombay) | 19.133, 72.916 | Serviceable: Powai, Dadar. Outside: rest. |
| 5 | Pune Trip | Pune (Koregaon Park) | 18.539, 73.892 | **Outside ALL** — exercises universal "outside delivery area" + 422 |

Each row writes a `CustomerAddress(customer_profile_id, address_id, label, is_default)` plus the underlying `Address` row.

## 3. One-shot bake script

**Path:** `backend/app/scripts/bake_mumbai_seed.py`

**Purpose:** convert author-time lat/lng approximations into authoritative Google data. Run once when authoring this PR (and again whenever locations change). Output is copied verbatim into `dev_seed.py` — the script itself is NOT called by `dev_seed`.

**Behavior:**

1. Iterate over a hard-coded list of `(label, lat, lng)` triples (the 9 stores + 5 customer addresses + 3 application addresses if needed, total 14–17 entries).
2. For each, call `GET /api/v1/geo/reverse?lat=&lng=` against the local backend (so the existing server-key + cache layer are exercised).
3. Parse response: take `place_id`, `formatted_address`, `latitude`, `longitude`, components → `city` (`locality` or `administrative_area_level_2`), `state` (`administrative_area_level_1`), `pincode` (`postal_code`).
4. **Country guard**: assert `short_name == "IN"` on the country component. Abort on mismatch.
5. Print one Python-literal dict per entry to stdout, with a banner separating stores from customer addresses.
6. On any non-200 response or `ZERO_RESULTS`, print the failed entry and abort with non-zero exit. No partial output committed.

**Run instructions** (added to script docstring + commit message):

```bash
# Stack must be running locally with Google key configured.
./scripts/dev.sh start
cd backend/app
uv run python scripts/bake_mumbai_seed.py > /tmp/baked.txt
# Inspect /tmp/baked.txt, paste into dev_seed.py.
```

## 4. `dev_seed.py` mutations

### 4.1 STORES list

Each existing entry's geo-related fields are overwritten with baked values. New fields added:

```python
{
    # existing keys: seller_idx, name, services, ...
    "address_line1": "<from Google formatted_address>",
    "address_line2": "<neighborhood, manually written for clarity>",
    "city": "Mumbai",
    "state": "Maharashtra",
    "pincode": "<from postal_code component>",
    "country": "India",
    "latitude": <float>,
    "longitude": <float>,
    "place_id": "<Google place_id>",
    "location_source": "pin",
    "delivery_radius_km": <float, per §1>,
    "pin_confirmed": True,
}
```

### 4.2 `_ADDRESS_KEYS`

Extend the existing tuple in `dev_seed.py` to include `place_id` and `location_source` so they're propagated into the seeded `Address` rows by `_upsert_address`.

### 4.3 `Store(...)` constructor

Pass `delivery_radius_km=store["delivery_radius_km"]` and `pin_confirmed=store["pin_confirmed"]`.

### 4.4 `CUSTOMER` dict + new seed step

```python
CUSTOMER: dict[str, Any] = {
    "email": "customer@khanabazaar.dev",
    "full_name": "Priya Verma",
    "phone": "+919811110200",
    "addresses": [
        {
            "label": "Home",
            "is_default": True,
            "address_line1": "...",
            "city": "Mumbai", "state": "Maharashtra", "pincode": "...",
            "country": "India",
            "latitude": ..., "longitude": ...,
            "place_id": "...",
            "location_source": "pin",
        },
        # 4 more entries
    ],
}
```

After `CustomerProfile` is created during seed, iterate `CUSTOMER["addresses"]`, create one `Address` row + one `CustomerAddress` row per entry. Exactly one address has `is_default=True`.

### 4.5 `_upsert_address` helper

Currently builds `Address` from a column dict. Extend to derive `digipin` from lat/lng if both present, mirroring `address_from_payload`. Cleanest implementation: import `address_from_payload` and route through it, OR import `digipin_encode` directly and add the missing field. Pick the latter — keeps seed independent of Pydantic validators.

```python
from app.utils.digipin import encode as digipin_encode

def _build_address_kwargs(data: Mapping[str, Any]) -> dict[str, Any]:
    out = {f: data.get(f) for f in _ADDRESS_KEYS}
    lat, lng = out.get("latitude"), out.get("longitude")
    if lat is not None and lng is not None:
        try:
            out["digipin"] = digipin_encode(lat, lng)
        except ValueError:
            out["digipin"] = None
    return out
```

`_upsert_address` calls `Address(**_build_address_kwargs(data))`.

## 5. Tests

`backend/app/tests/test_dev_seed.py` (file already exists). Add four cases:

1. `test_customer_has_five_addresses_with_default_home` — query `CustomerAddress` for the seeded customer; assert 5 rows; assert exactly one `is_default=True` and its label is "Home".
2. `test_all_seeded_stores_in_mumbai_with_pin_confirmed` — assert 9 stores; for each: lat ∈ (18.8, 19.3), lng ∈ (72.7, 73.0), `digipin is not None`, `pin_confirmed is True`, `delivery_radius_km > 0`.
3. `test_bandra_home_is_serviceable_for_sharma_store` — direct PostGIS `ST_DWithin` query; assert True.
4. `test_pune_address_is_not_serviceable_for_any_store` — iterate all stores; assert `ST_DWithin` is False for every one.

The existing seed-tests use a `_seed_database` fixture that runs the dev seed against the test DB — re-use it.

## 6. Edge cases & error handling

| Case | Handling |
|---|---|
| Google reverse-geocode `ZERO_RESULTS` during bake | Script aborts loudly with the failing lat/lng; no partial data committed |
| Country component non-IN | Script asserts `short_name == "IN"`, aborts |
| `pincode` component missing (rare for urban Mumbai) | Bake script logs warning; I fix manually before pasting |
| Lat/lng outside India bbox at seed time (only Pune) | Pune is inside bbox (lat 18.5 ∈ [2.5, 38.5]). DIGIPIN derives normally. |
| Seed re-run on existing DB | Existing flow (`local_reset.py`) wipes everything first; idempotent runs are out of scope |
| `_upsert_address` deduplication | Existing dedup is by full column tuple; new addresses are unique by `address_line1` |
| `pin_confirmed=true` with null lat/lng | Cannot occur — bake guarantees lat/lng for every seeded entry |

## 7. Manual QA checklist (post-merge smoke test)

- [ ] `./scripts/dev.sh restart` + `./scripts/reset_local_state.sh` to apply fresh seed
- [ ] Login as `customer@khanabazaar.dev` (console OTP)
- [ ] **Account → Settings**: see 5 addresses; Home flagged default
- [ ] **/stores with no chip**: 9 stores listed, no `distance_km`
- [ ] **Chip → Home (Bandra)**: list re-orders by distance; Juhu (1 km) drops out; Sharma top
- [ ] **Chip → Pune (~150 km)**: empty state "No stores deliver here yet"
- [ ] **Sharma checkout**: Home + Office enabled; Pune greyed "Outside delivery area"
- [ ] **Direct API bypass**: `curl -X POST /api/v1/orders` with Pune address → 422 `Address outside store delivery area`
- [ ] Login as `seller@` → dashboard banner cleared (pin_confirmed=true); radius slider at 5 km

## 8. Out of scope

- Backfilling the 3 application addresses (`pending.seller@`, `approved.seller@`, `rejected.seller@`) with real lat/lng. They keep `latitude=None`/`longitude=None`. Their stores are not auto-created until admin approves, which won't happen in seed.
- Adding more sellers or stores. Existing 9 are reused.
- Changing inventory or service mappings.
- Making `dev_seed.py` idempotent (already a separate concern).
