"""One-shot author-time bake script for Mumbai seed data.

Calls the local /api/v1/geo/reverse endpoint for each landmark and prints
Python-literal dicts to stdout. Output is meant to be copied verbatim into
`app/db/dev_seed.py`. The script itself is NOT part of the recurring seed
flow — recurring `python -m app.db.dev_seed` runs never touch Google.

Usage:
    ./scripts/dev.sh start
    cd backend/app
    uv run python scripts/bake_mumbai_seed.py > /tmp/baked.txt
    # Inspect /tmp/baked.txt, paste the dicts into app/db/dev_seed.py.

Aborts loudly on any non-IN result, ZERO_RESULTS, or HTTP failure.
"""
from __future__ import annotations

import json
import sys
from typing import Any

import httpx

BACKEND = "http://localhost:8000"


# (kind, label, lat, lng, extra_fields) — extras propagate into output dict.
ENTRIES: list[tuple[str, str, float, float, dict[str, Any]]] = [
    # ---- 9 stores (one per existing seller_idx 1..9) ----
    ("store", "Sharma General Store", 19.060, 72.831,
     {"seller_idx": 1, "delivery_radius_km": 5.0, "address_line2": "Bandra West"}),
    ("store", "Krishna Supermart", 19.135, 72.829,
     {"seller_idx": 2, "delivery_radius_km": 3.0, "address_line2": "Andheri West"}),
    ("store", "Balaji Fresh Market", 18.910, 72.815,
     {"seller_idx": 3, "delivery_radius_km": 2.0, "address_line2": "Colaba"}),
    ("store", "Powai Pulse Pharmacy", 19.117, 72.910,
     {"seller_idx": 4, "delivery_radius_km": 8.0, "address_line2": "Powai"}),
    ("store", "Worli Daily Needs", 19.018, 72.815,
     {"seller_idx": 5, "delivery_radius_km": 5.0, "address_line2": "Worli"}),
    ("store", "Juhu Beach Bites", 19.099, 72.826,
     {"seller_idx": 6, "delivery_radius_km": 1.0, "address_line2": "Juhu"}),
    ("store", "Dadar Dawakhana", 19.018, 72.844,
     {"seller_idx": 7, "delivery_radius_km": 15.0, "address_line2": "Dadar West"}),
    ("store", "Lower Parel Larder", 18.998, 72.829,
     {"seller_idx": 8, "delivery_radius_km": 4.0, "address_line2": "Lower Parel"}),
    ("store", "Goregaon Grocers", 19.165, 72.851,
     {"seller_idx": 9, "delivery_radius_km": 3.0, "address_line2": "Goregaon East"}),

    # ---- 5 customer addresses (customer@khanabazaar.dev) ----
    ("customer", "Home", 19.062, 72.835,
     {"label": "Home", "is_default": True, "address_line2": "Bandra West"}),
    ("customer", "Office", 19.001, 72.829,
     {"label": "Office", "is_default": False, "address_line2": "Lower Parel"}),
    ("customer", "Friend's Place", 19.122, 72.870,
     {"label": "Friend's Place", "is_default": False, "address_line2": "Andheri East"}),
    ("customer", "Parents", 19.133, 72.916,
     {"label": "Parents", "is_default": False, "address_line2": "Powai"}),
    ("customer", "Pune Trip", 18.539, 73.892,
     {"label": "Pune Trip", "is_default": False, "address_line2": "Koregaon Park"}),
]


def _component(components: list[dict[str, Any]], type_: str) -> str | None:
    for c in components:
        if type_ in c.get("types", []):
            return c.get("long_name") or c.get("short_name")
    return None


def reverse_geocode(lat: float, lng: float) -> dict[str, Any]:
    r = httpx.get(
        f"{BACKEND}/api/v1/geo/reverse",
        params={"lat": lat, "lng": lng},
        timeout=15.0,
    )
    r.raise_for_status()
    return r.json()


def parse_one(
    kind: str, name: str, lat: float, lng: float, extras: dict[str, Any],
) -> dict[str, Any]:
    body = reverse_geocode(lat, lng)
    components = body.get("components", [])
    country = _component(components, "country")
    if country and country.upper() not in {"INDIA", "IN"}:
        sys.exit(f"ABORT: {name} resolved to country={country!r}, not India")

    state = (
        _component(components, "administrative_area_level_1")
        or "Maharashtra"
    )
    city = (
        _component(components, "locality")
        or _component(components, "administrative_area_level_2")
        or "Mumbai"
    )
    pincode = _component(components, "postal_code")
    if not pincode:
        sys.exit(f"ABORT: {name} missing postal_code; components={components!r}")

    formatted = body["formatted_address"]
    address_line1 = formatted.split(",")[0].strip()

    out: dict[str, Any] = {
        "name": name,
        "address_line1": address_line1,
        "address_line2": extras.get("address_line2"),
        "landmark": None,
        "city": city,
        "state": state,
        "pincode": pincode,
        "country": "India",
        "latitude": float(body["latitude"]),
        "longitude": float(body["longitude"]),
        "place_id": body.get("place_id"),
        "location_source": "pin",
    }
    # carry extras (seller_idx, delivery_radius_km, label, is_default, ...)
    for k, v in extras.items():
        if k == "address_line2":
            continue  # already merged
        out[k] = v
    return out


def main() -> None:
    stores: list[dict[str, Any]] = []
    customer_addrs: list[dict[str, Any]] = []
    for kind, name, lat, lng, extras in ENTRIES:
        rec = parse_one(kind, name, lat, lng, extras)
        if kind == "store":
            stores.append(rec)
        else:
            customer_addrs.append(rec)

    print("# === STORES ===")
    print("STORES = [")
    for s in stores:
        print(f"    {json.dumps(s, ensure_ascii=False)},")
    print("]")
    print()
    print("# === CUSTOMER ADDRESSES ===")
    print("CUSTOMER_ADDRESSES = [")
    for a in customer_addrs:
        print(f"    {json.dumps(a, ensure_ascii=False)},")
    print("]")


if __name__ == "__main__":
    main()
