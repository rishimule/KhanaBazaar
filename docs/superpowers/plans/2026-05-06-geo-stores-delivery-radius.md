<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Geo-aware Stores, Delivery Radius, Address Mapping — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sort stores by real-world distance, gate orders by per-store delivery radius, and capture courier-grade location data (lat/lng + Google Place ID + DIGIPIN) on every address via UberEats-style autocomplete + map-pin UX.

**Architecture:** PostGIS `geography` (generated column on `Address`) + GiST index drives `ST_DWithin` filtering and `ST_Distance` sorting. Google Maps Platform proxied through backend (`/api/v1/geo/*`) so the API key never reaches the browser; only the referrer-restricted browser key powers map render via `@vis.gl/react-google-maps`. DIGIPIN derived in pure Python from lat/lng on every address write. Soft address verification: serviceability is checked at use-time, not save-time.

**Tech Stack:** PostGIS 3.4, Alembic, SQLModel, FastAPI, httpx (no Google SDK), Redis (cache + rate-limit), Celery (backfill), Next.js 16 + React 19, `@vis.gl/react-google-maps`, CSS Modules.

**Spec:** `docs/superpowers/specs/2026-05-06-geo-stores-delivery-radius-design.md`.

**Branch:** `feat/geo-stores-delivery-radius` (already created).

---

## Phase 0 — Local infra: PostGIS-enabled Postgres

### Task 1: Swap docker-compose Postgres image to PostGIS variant

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docs/local_setup.md`

- [ ] **Step 1: Edit docker-compose.yml**

Replace `postgres:15` with `postgis/postgis:15-3.4`. The image is binary-compatible with `postgres:15` (same data dir layout) but adds the PostGIS extension binaries.

```yaml
  postgres:
    image: postgis/postgis:15-3.4
    container_name: khanabazaar-postgres
    restart: always
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
      POSTGRES_DB: khanabazaar
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

- [ ] **Step 2: Add a setup note to docs/local_setup.md**

Append a section explaining the one-time recreate:

```markdown
### PostGIS upgrade (May 2026 onward)

The Postgres image was upgraded to `postgis/postgis:15-3.4`. If you have an existing local volume from the plain `postgres:15` image, recreate it once:

```bash
docker-compose down -v
docker-compose up -d
cd backend/app
uv run alembic upgrade head
```
```

- [ ] **Step 3: Recreate the local stack and verify PostGIS available**

```bash
docker-compose down -v
docker-compose up -d
sleep 3
docker exec khanabazaar-postgres psql -U postgres -d khanabazaar -c "SELECT name FROM pg_available_extensions WHERE name='postgis';"
```

Expected: one row returned with `postgis`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml docs/local_setup.md
git commit -m "chore(infra): switch local Postgres image to postgis/postgis:15-3.4"
```

---

### Task 2: Enable PostGIS extension in test database setup

**Files:**
- Modify: `backend/app/tests/conftest.py`

- [ ] **Step 1: Locate the test DB setup hook**

Read `backend/app/tests/conftest.py`. Find the fixture/function that creates schema (likely runs `SQLModel.metadata.create_all` or applies migrations).

- [ ] **Step 2: Add `CREATE EXTENSION IF NOT EXISTS postgis;` before schema creation**

Inside the same async engine context that drops + recreates tables, run the extension statement first. Use raw SQL via the engine connection:

```python
from sqlalchemy import text

async with engine.begin() as conn:
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    await conn.run_sync(SQLModel.metadata.drop_all)
    await conn.run_sync(SQLModel.metadata.create_all)
```

- [ ] **Step 3: Verify the existing test suite still passes**

```bash
cd backend/app
docker-compose -f ../../docker-compose.yml up -d
createdb -h localhost -U postgres khanabazaar_test 2>/dev/null || true
uv run pytest -v -x
```

Expected: existing tests pass (no behavior change yet — just an additional `CREATE EXTENSION` call).

- [ ] **Step 4: Commit**

```bash
git add backend/app/tests/conftest.py
git commit -m "test: enable postgis extension in test database setup"
```

---

## Phase 1 — DIGIPIN module (TDD)

### Task 3: Write failing tests for DIGIPIN encode

**Files:**
- Create: `backend/app/tests/test_digipin.py`

- [ ] **Step 1: Write the test file with known landmark encodings**

```python
"""Tests for India Post DIGIPIN encode/decode (10-char alphanumeric grid code).

Reference algorithm: India Post / IIT-Hyderabad. Bounds: lat 2.5-38.5, lng 63.5-99.5.
"""
import pytest

from app.utils.digipin import decode, encode


# Landmarks with DIGIPINs verified against the official India Post reference encoder.
LANDMARKS: list[tuple[str, float, float, str]] = [
    ("India Gate, New Delhi", 28.6129, 77.2295, "39J-49L-L8T4"),
    ("Gateway of India, Mumbai", 18.9220, 72.8347, "4FK-595-9CC4"),
    ("Charminar, Hyderabad", 17.3616, 78.4747, "422-4P9-FK5T"),
]


@pytest.mark.parametrize("name,lat,lng,expected", LANDMARKS)
def test_encode_known_landmarks(name: str, lat: float, lng: float, expected: str) -> None:
    assert encode(lat, lng) == expected, name


def test_encode_returns_10_chars_with_dashes() -> None:
    code = encode(28.6129, 77.2295)
    assert len(code) == 12  # 10 chars + 2 dashes
    assert code.count("-") == 2
    cleaned = code.replace("-", "")
    assert len(cleaned) == 10


@pytest.mark.parametrize(
    "lat,lng",
    [
        (0.0, 75.0),     # below min lat
        (40.0, 75.0),    # above max lat
        (20.0, 60.0),    # below min lng
        (20.0, 100.0),   # above max lng
    ],
)
def test_encode_rejects_out_of_bounds(lat: float, lng: float) -> None:
    with pytest.raises(ValueError):
        encode(lat, lng)
```

> **Note:** the expected DIGIPIN strings above are illustrative. Before checking in this test file, run the official India Post reference encoder on the three landmark coordinates and substitute the actual codes. The implementation must match the reference, not these placeholders.

- [ ] **Step 2: Run test to verify it fails with import error**

```bash
cd backend/app
uv run pytest tests/test_digipin.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.utils.digipin'`.

- [ ] **Step 3: Commit the failing tests**

```bash
git add backend/app/tests/test_digipin.py
git commit -m "test: add failing tests for digipin encode + bounds"
```

---

### Task 4: Implement DIGIPIN encode

**Files:**
- Create: `backend/app/src/app/utils/digipin.py`

- [ ] **Step 1: Implement encode() per India Post 4×4 grid recursion**

```python
"""India Post DIGIPIN encode/decode.

Open algorithm published by India Post / IIT-Hyderabad. Encodes a lat/lng
inside the India bounding box (2.5-38.5 lat, 63.5-99.5 lng) into a 10-char
alphanumeric grid code rendered as `XXX-XXX-XXXX`. Each character narrows
the cell by a factor of 4x4 (16 cells per level, 10 levels deep, ~3.8m
final precision).
"""
from __future__ import annotations

# 4x4 character matrix as published by India Post.
_GRID: tuple[tuple[str, ...], ...] = (
    ("F", "C", "9", "8"),
    ("J", "3", "2", "7"),
    ("K", "4", "5", "6"),
    ("L", "M", "P", "T"),
)

_LAT_MIN, _LAT_MAX = 2.5, 38.5
_LNG_MIN, _LNG_MAX = 63.5, 99.5
_LEVELS = 10


def _flatten(code: str) -> str:
    return code.replace("-", "")


def encode(lat: float, lng: float) -> str:
    """Return the DIGIPIN for a lat/lng inside the India bounding box.

    Raises:
        ValueError: lat or lng outside the India bbox.
    """
    if not (_LAT_MIN <= lat <= _LAT_MAX):
        raise ValueError(f"latitude {lat} outside India bbox [{_LAT_MIN}, {_LAT_MAX}]")
    if not (_LNG_MIN <= lng <= _LNG_MAX):
        raise ValueError(f"longitude {lng} outside India bbox [{_LNG_MIN}, {_LNG_MAX}]")

    lat_lo, lat_hi = _LAT_MIN, _LAT_MAX
    lng_lo, lng_hi = _LNG_MIN, _LNG_MAX
    chars: list[str] = []

    for _ in range(_LEVELS):
        lat_step = (lat_hi - lat_lo) / 4.0
        lng_step = (lng_hi - lng_lo) / 4.0
        # Row index 0 is the TOP of the cell (highest latitude).
        row = 3 - min(int((lat - lat_lo) / lat_step), 3)
        col = min(int((lng - lng_lo) / lng_step), 3)
        chars.append(_GRID[row][col])

        new_lat_lo = lat_hi - (row + 1) * lat_step
        new_lat_hi = lat_hi - row * lat_step
        new_lng_lo = lng_lo + col * lng_step
        new_lng_hi = lng_lo + (col + 1) * lng_step
        lat_lo, lat_hi = new_lat_lo, new_lat_hi
        lng_lo, lng_hi = new_lng_lo, new_lng_hi

    raw = "".join(chars)
    return f"{raw[:3]}-{raw[3:6]}-{raw[6:]}"
```

- [ ] **Step 2: Run encode tests; expect pass**

```bash
cd backend/app
uv run pytest tests/test_digipin.py::test_encode_returns_10_chars_with_dashes tests/test_digipin.py::test_encode_rejects_out_of_bounds -v
```

Expected: PASS for the format and bounds tests. The landmark test passes only after the placeholder DIGIPINs in the test file are replaced with the official reference output (do that now before continuing).

- [ ] **Step 3: Run full digipin suite; expect all pass**

```bash
uv run pytest tests/test_digipin.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/src/app/utils/digipin.py backend/app/tests/test_digipin.py
git commit -m "feat(utils): add digipin encode with india bbox guard"
```

---

### Task 5: Add DIGIPIN decode + round-trip test

**Files:**
- Modify: `backend/app/src/app/utils/digipin.py`
- Modify: `backend/app/tests/test_digipin.py`

- [ ] **Step 1: Add the failing round-trip test**

Append to `test_digipin.py`:

```python
@pytest.mark.parametrize("name,lat,lng,_", LANDMARKS)
def test_decode_round_trip(name: str, lat: float, lng: float, _: str) -> None:
    code = encode(lat, lng)
    out_lat, out_lng = decode(code)
    # Cell precision at level 10 is ~3.8m; allow ~5m absolute tolerance.
    assert abs(out_lat - lat) < 5e-5, f"{name}: lat drift"
    assert abs(out_lng - lng) < 5e-5, f"{name}: lng drift"


def test_decode_invalid_chars_rejected() -> None:
    with pytest.raises(ValueError):
        decode("ZZZ-ZZZ-ZZZZ")


def test_decode_wrong_length_rejected() -> None:
    with pytest.raises(ValueError):
        decode("ABC")
```

- [ ] **Step 2: Run; expect failure (decode not defined yet)**

```bash
cd backend/app
uv run pytest tests/test_digipin.py::test_decode_round_trip -v
```

Expected: `ImportError` or `AttributeError: module ... has no attribute 'decode'`.

- [ ] **Step 3: Implement decode()**

Add to `digipin.py`:

```python
_CHAR_TO_RC: dict[str, tuple[int, int]] = {
    ch: (r, c)
    for r, row in enumerate(_GRID)
    for c, ch in enumerate(row)
}


def decode(code: str) -> tuple[float, float]:
    """Return the lat/lng of the cell centre for a DIGIPIN.

    Raises:
        ValueError: code is the wrong length or contains invalid characters.
    """
    raw = _flatten(code).upper()
    if len(raw) != _LEVELS:
        raise ValueError(f"DIGIPIN must be {_LEVELS} chars excluding dashes")

    lat_lo, lat_hi = _LAT_MIN, _LAT_MAX
    lng_lo, lng_hi = _LNG_MIN, _LNG_MAX

    for ch in raw:
        if ch not in _CHAR_TO_RC:
            raise ValueError(f"invalid DIGIPIN char {ch!r}")
        row, col = _CHAR_TO_RC[ch]
        lat_step = (lat_hi - lat_lo) / 4.0
        lng_step = (lng_hi - lng_lo) / 4.0
        new_lat_hi = lat_hi - row * lat_step
        new_lat_lo = lat_hi - (row + 1) * lat_step
        new_lng_lo = lng_lo + col * lng_step
        new_lng_hi = lng_lo + (col + 1) * lng_step
        lat_lo, lat_hi = new_lat_lo, new_lat_hi
        lng_lo, lng_hi = new_lng_lo, new_lng_hi

    return (lat_lo + lat_hi) / 2.0, (lng_lo + lng_hi) / 2.0
```

- [ ] **Step 4: Run all digipin tests; expect pass**

```bash
uv run pytest tests/test_digipin.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/utils/digipin.py backend/app/tests/test_digipin.py
git commit -m "feat(utils): add digipin decode + round-trip test"
```

---

## Phase 2 — Schema migrations + model updates

### Task 6: Alembic migration — enable PostGIS extension

**Files:**
- Create: `backend/app/migrations/versions/<auto>_enable_postgis.py`

- [ ] **Step 1: Generate empty revision**

```bash
cd backend/app
uv run alembic revision -m "enable_postgis"
```

- [ ] **Step 2: Edit the generated revision**

```python
"""enable_postgis"""
from alembic import op

revision = "<keep generated>"
down_revision = "<keep generated>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS postgis")
```

- [ ] **Step 3: Apply and verify**

```bash
uv run alembic upgrade head
docker exec khanabazaar-postgres psql -U postgres -d khanabazaar -c "SELECT extname FROM pg_extension WHERE extname='postgis';"
```

Expected: `postgis` returned.

- [ ] **Step 4: Commit**

```bash
git add backend/app/migrations/versions/*_enable_postgis.py
git commit -m "feat(db): migration to enable postgis extension"
```

---

### Task 7: Add new Address columns to model + migration

**Files:**
- Modify: `backend/app/src/app/models/address.py`
- Create: `backend/app/migrations/versions/<auto>_address_geo_columns.py`

- [ ] **Step 1: Update the model**

Replace the contents of `backend/app/src/app/models/address.py`:

```python
import enum
from typing import Optional

from sqlalchemy import Column, Enum as SAEnum, String
from sqlmodel import Field

from app.models.base import BaseSchema


class LocationSource(str, enum.Enum):
    manual = "manual"
    autocomplete = "autocomplete"
    pin = "pin"
    geocoded = "geocoded"


class Address(BaseSchema, table=True):
    address_line1: str = Field(nullable=False, max_length=120)
    address_line2: Optional[str] = Field(default=None, nullable=True, max_length=120)
    landmark: Optional[str] = Field(default=None, nullable=True, max_length=120)
    city: str = Field(nullable=False, max_length=80)
    state: str = Field(nullable=False, max_length=80)
    pincode: str = Field(nullable=False, max_length=10)
    country: str = Field(nullable=False, default="India", max_length=60)
    latitude: Optional[float] = Field(default=None, nullable=True)
    longitude: Optional[float] = Field(default=None, nullable=True)
    digipin: Optional[str] = Field(default=None, nullable=True, max_length=12)
    place_id: Optional[str] = Field(default=None, nullable=True, max_length=255)
    location_source: Optional[LocationSource] = Field(
        default=None,
        nullable=True,
        sa_column=Column(SAEnum(LocationSource, name="locationsource"), nullable=True),
    )
    # Note: `geo` is a Postgres GENERATED column added in a separate migration.
    # SQLModel does not need to declare it; reads happen via raw SQL in the
    # store-listing query.
```

- [ ] **Step 2: Generate migration**

```bash
cd backend/app
uv run alembic revision --autogenerate -m "address_geo_columns"
```

- [ ] **Step 3: Hand-edit the migration to add the generated `geo` column after the regular columns**

After the auto-generated `add_column` calls for `digipin`, `place_id`, `location_source`, append:

```python
    op.execute(
        "ALTER TABLE address ADD COLUMN geo geography(Point, 4326) "
        "GENERATED ALWAYS AS ("
        "  CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL "
        "       THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography "
        "       ELSE NULL END"
        ") STORED"
    )
    op.execute("CREATE INDEX ix_address_geo ON address USING GIST (geo)")
```

In the matching `downgrade()`:

```python
    op.execute("DROP INDEX IF EXISTS ix_address_geo")
    op.execute("ALTER TABLE address DROP COLUMN geo")
```

- [ ] **Step 4: Apply and verify**

```bash
uv run alembic upgrade head
docker exec khanabazaar-postgres psql -U postgres -d khanabazaar -c "\d address"
```

Expected: columns `digipin`, `place_id`, `location_source`, `geo` all present; `geo` shown as generated.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/models/address.py backend/app/migrations/versions/*_address_geo_columns.py
git commit -m "feat(db): add digipin/place_id/location_source/geo columns on address"
```

---

### Task 8: Add new Store columns + migration

**Files:**
- Modify: `backend/app/src/app/models/store.py`
- Create: `backend/app/migrations/versions/<auto>_store_delivery_radius.py`

- [ ] **Step 1: Update the Store model**

```python
from sqlmodel import Field, Relationship, UniqueConstraint

from app.models.address import Address
from app.models.base import BaseSchema
from app.models.catalog import MasterProduct
from app.models.profile import SellerProfile


class Store(BaseSchema, table=True):
    __table_args__ = (UniqueConstraint("seller_profile_id", name="uq_store_seller_profile"),)
    name: str = Field(index=True, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    seller_profile_id: int = Field(foreign_key="sellerprofile.id", nullable=False, index=True)
    address_id: int = Field(foreign_key="address.id", nullable=False, index=True)
    delivery_radius_km: float = Field(default=5.0, nullable=False)
    pin_confirmed: bool = Field(default=False, nullable=False)

    seller_profile: SellerProfile = Relationship()
    address: Address = Relationship()


class StoreInventory(BaseSchema, table=True):
    __table_args__ = (UniqueConstraint("store_id", "product_id", name="uq_store_product"),)
    store_id: int = Field(foreign_key="store.id", nullable=False)
    product_id: int = Field(foreign_key="masterproduct.id", nullable=False)
    price: float = Field(nullable=False)
    stock: int = Field(default=0, nullable=False)
    is_available: bool = Field(default=True, nullable=False)

    store: Store = Relationship()
    product: MasterProduct = Relationship()
```

- [ ] **Step 2: Generate migration**

```bash
cd backend/app
uv run alembic revision --autogenerate -m "store_delivery_radius_pin_confirmed"
```

- [ ] **Step 3: Inspect & confirm the auto-generated migration sets defaults correctly**

The migration should include `server_default=sa.text("5.0")` for `delivery_radius_km` and `server_default=sa.text("false")` for `pin_confirmed` so existing rows backfill. If autogen omitted them, hand-edit:

```python
op.add_column(
    "store",
    sa.Column("delivery_radius_km", sa.Float(), nullable=False, server_default=sa.text("5.0")),
)
op.add_column(
    "store",
    sa.Column("pin_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
)
```

- [ ] **Step 4: Apply and commit**

```bash
uv run alembic upgrade head
git add backend/app/src/app/models/store.py backend/app/migrations/versions/*_store_delivery_radius_pin_confirmed.py
git commit -m "feat(db): add delivery_radius_km + pin_confirmed on store"
```

---

### Task 9: Update AddressPayload + address_from_payload to handle new fields and DIGIPIN

**Files:**
- Modify: `backend/app/src/app/schemas/address.py`
- Create: `backend/app/tests/test_address_from_payload.py`

- [ ] **Step 1: Write failing test for DIGIPIN auto-derivation**

```python
"""Tests for the address_from_payload helper, focused on DIGIPIN derivation."""
import pytest

from app.schemas.address import AddressPayload, address_from_payload


def _payload(**kwargs: object) -> AddressPayload:
    base = dict(
        address_line1="1, Main Rd",
        city="Mumbai",
        state="Maharashtra",
        pincode="400001",
        country="India",
    )
    base.update(kwargs)
    return AddressPayload(**base)


def test_no_lat_lng_yields_null_digipin() -> None:
    out = address_from_payload(_payload())
    assert out["digipin"] is None
    assert out["latitude"] is None
    assert out["longitude"] is None


def test_lat_lng_inside_india_yields_digipin() -> None:
    out = address_from_payload(_payload(latitude=18.9220, longitude=72.8347))
    assert isinstance(out["digipin"], str)
    assert len(out["digipin"]) == 12  # 10 chars + 2 dashes


def test_lat_lng_outside_india_yields_null_digipin() -> None:
    out = address_from_payload(_payload(latitude=51.5074, longitude=-0.1278))
    # London is outside India bbox; encode raises, helper swallows -> null.
    assert out["digipin"] is None


def test_extra_fields_round_trip() -> None:
    out = address_from_payload(
        _payload(latitude=18.9, longitude=72.8)
    )
    # New optional fields default to None when payload omits them
    assert out["place_id"] is None
    assert out["location_source"] is None


@pytest.mark.parametrize("source", ["manual", "autocomplete", "pin", "geocoded"])
def test_location_source_passthrough(source: str) -> None:
    out = address_from_payload(_payload(location_source=source))
    assert out["location_source"] == source
```

- [ ] **Step 2: Run; expect import / attribute errors**

```bash
cd backend/app
uv run pytest tests/test_address_from_payload.py -v
```

Expected: failures because new fields don't exist on `AddressPayload`.

- [ ] **Step 3: Update AddressPayload + helper**

Replace the relevant sections of `backend/app/src/app/schemas/address.py`:

```python
from app.models.address import LocationSource
from app.utils.digipin import encode as digipin_encode


class AddressPayload(BaseModel):
    address_line1: str = Field(min_length=1, max_length=120)
    address_line2: Optional[str] = Field(default=None, max_length=120)
    landmark: Optional[str] = Field(default=None, max_length=120)
    city: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=80)
    pincode: str = Field(min_length=3, max_length=10)
    country: str = Field(default="India", min_length=1, max_length=60)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    place_id: Optional[str] = Field(default=None, max_length=255)
    location_source: Optional[LocationSource] = None

    @model_validator(mode="after")
    def _check_country_specific_rules(self) -> "AddressPayload":
        # ... existing body unchanged ...
        return self


_ADDRESS_FIELDS: tuple[str, ...] = (
    "address_line1",
    "address_line2",
    "landmark",
    "city",
    "state",
    "pincode",
    "country",
    "latitude",
    "longitude",
    "place_id",
    "location_source",
)


def address_from_payload(payload: AddressPayload) -> dict[str, object]:
    """Flatten the nested payload + derive DIGIPIN from lat/lng if both present."""
    out: dict[str, object] = {field: getattr(payload, field) for field in _ADDRESS_FIELDS}
    digipin: Optional[str] = None
    if payload.latitude is not None and payload.longitude is not None:
        try:
            digipin = digipin_encode(payload.latitude, payload.longitude)
        except ValueError:
            digipin = None  # outside India bbox — keep address but skip code
    out["digipin"] = digipin
    return out


def address_to_payload(owner: object) -> AddressPayload:
    """Build a nested payload from an owner object carrying the flat columns."""
    return AddressPayload(
        **{field: getattr(owner, field) for field in _ADDRESS_FIELDS}
    )
```

- [ ] **Step 4: Run new + existing address tests; expect pass**

```bash
uv run pytest tests/test_address_from_payload.py tests/test_address_validator.py tests/test_format_address.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/schemas/address.py backend/app/tests/test_address_from_payload.py
git commit -m "feat(schemas): derive digipin in address_from_payload, accept place_id/location_source"
```

---

## Phase 3 — Backend Google proxy + geo endpoints

### Task 10: Config additions for Google API keys

**Files:**
- Modify: `backend/app/src/app/core/config.py`
- Modify: `backend/app/.env.example`

- [ ] **Step 1: Add settings fields**

In `core/config.py`, inside the Settings class:

```python
GOOGLE_MAPS_SERVER_API_KEY: str = ""
GOOGLE_MAPS_BROWSER_API_KEY: str = ""  # exposed to frontend; referrer-restricted
GEO_RATE_LIMIT_PER_MIN: int = 30
GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS: int = 60
GEO_REVERSE_CACHE_TTL_SECONDS: int = 86400
```

- [ ] **Step 2: Add the keys to `.env.example`**

```
# Google Maps (geocoding, autocomplete, reverse). Server key is IP-restricted in GCP console.
GOOGLE_MAPS_SERVER_API_KEY=
GOOGLE_MAPS_BROWSER_API_KEY=
GEO_RATE_LIMIT_PER_MIN=30
GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS=60
GEO_REVERSE_CACHE_TTL_SECONDS=86400
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/src/app/core/config.py backend/app/.env.example
git commit -m "feat(config): add google maps + geo cache/rate-limit settings"
```

---

### Task 11: Google client wrapper (httpx, no SDK)

**Files:**
- Create: `backend/app/src/app/core/google_maps.py`
- Create: `backend/app/tests/test_google_maps_client.py`

- [ ] **Step 1: Write the failing test (mock httpx client)**

```python
"""Tests for the thin Google Maps Platform client wrapper."""
from typing import Any

import httpx
import pytest

from app.core.google_maps import (
    GoogleMapsClient,
    GoogleMapsError,
    autocomplete,
    place_details,
    reverse_geocode,
)


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self._status = status

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self._status, json=self._payload, request=request)


@pytest.mark.asyncio
async def test_autocomplete_parses_predictions() -> None:
    client = GoogleMapsClient(
        api_key="test",
        transport=_MockTransport({
            "status": "OK",
            "predictions": [
                {"place_id": "p1", "description": "A, India"},
                {"place_id": "p2", "description": "B, India"},
            ],
        }),
    )
    out = await autocomplete(client, query="andheri", session_token="s1")
    assert len(out) == 2
    assert out[0].place_id == "p1"
    assert out[0].description == "A, India"


@pytest.mark.asyncio
async def test_place_details_returns_lat_lng() -> None:
    client = GoogleMapsClient(
        api_key="test",
        transport=_MockTransport({
            "status": "OK",
            "result": {
                "place_id": "p1",
                "formatted_address": "X",
                "geometry": {"location": {"lat": 18.9, "lng": 72.8}},
                "address_components": [],
            },
        }),
    )
    out = await place_details(client, place_id="p1", session_token="s1")
    assert out.latitude == 18.9
    assert out.longitude == 72.8
    assert out.formatted_address == "X"


@pytest.mark.asyncio
async def test_reverse_geocode_returns_first_result() -> None:
    client = GoogleMapsClient(
        api_key="test",
        transport=_MockTransport({
            "status": "OK",
            "results": [
                {
                    "formatted_address": "Y",
                    "address_components": [],
                    "geometry": {"location": {"lat": 18.9, "lng": 72.8}},
                    "place_id": "p2",
                },
            ],
        }),
    )
    out = await reverse_geocode(client, lat=18.9, lng=72.8)
    assert out.formatted_address == "Y"


@pytest.mark.asyncio
async def test_zero_results_raises() -> None:
    client = GoogleMapsClient(
        api_key="test",
        transport=_MockTransport({"status": "ZERO_RESULTS", "results": []}),
    )
    with pytest.raises(GoogleMapsError):
        await reverse_geocode(client, lat=0.0, lng=0.0)
```

- [ ] **Step 2: Run; expect import error**

```bash
cd backend/app
uv run pytest tests/test_google_maps_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.core.google_maps'`.

- [ ] **Step 3: Implement the client**

```python
"""Thin async Google Maps Platform client.

Direct httpx calls — no Google SDK dependency. Each function returns a
typed dataclass; callers are responsible for caching/rate-limiting.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx


class GoogleMapsError(Exception):
    """Raised on non-OK status from any Google Maps endpoint."""


@dataclass(frozen=True)
class AddressComponent:
    long_name: str
    short_name: str
    types: tuple[str, ...]


@dataclass(frozen=True)
class Prediction:
    place_id: str
    description: str


@dataclass(frozen=True)
class Place:
    place_id: str
    formatted_address: str
    latitude: float
    longitude: float
    components: tuple[AddressComponent, ...]


_BASE = "https://maps.googleapis.com/maps/api"


class GoogleMapsClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout: float = 5.0,
    ) -> None:
        self._key = api_key
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    async def get(self, path: str, params: dict[str, str]) -> dict:
        params = {**params, "key": self._key}
        resp = await self._client.get(f"{_BASE}{path}", params=params)
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") not in {"OK", "ZERO_RESULTS"}:
            raise GoogleMapsError(f"google maps: {body.get('status')}: {body.get('error_message', '')}")
        return body

    async def aclose(self) -> None:
        await self._client.aclose()


def _components(raw: list[dict]) -> tuple[AddressComponent, ...]:
    return tuple(
        AddressComponent(
            long_name=c.get("long_name", ""),
            short_name=c.get("short_name", ""),
            types=tuple(c.get("types", [])),
        )
        for c in raw
    )


async def autocomplete(
    client: GoogleMapsClient, *, query: str, session_token: str
) -> list[Prediction]:
    body = await client.get(
        "/place/autocomplete/json",
        {
            "input": query,
            "sessiontoken": session_token,
            "components": "country:in",
        },
    )
    if body.get("status") == "ZERO_RESULTS":
        return []
    return [
        Prediction(place_id=p["place_id"], description=p["description"])
        for p in body.get("predictions", [])
    ]


async def place_details(
    client: GoogleMapsClient, *, place_id: str, session_token: str
) -> Place:
    body = await client.get(
        "/place/details/json",
        {
            "place_id": place_id,
            "sessiontoken": session_token,
            "fields": "place_id,formatted_address,geometry/location,address_components",
        },
    )
    if body.get("status") == "ZERO_RESULTS":
        raise GoogleMapsError(f"no place details for {place_id}")
    r = body["result"]
    loc = r["geometry"]["location"]
    return Place(
        place_id=r["place_id"],
        formatted_address=r.get("formatted_address", ""),
        latitude=float(loc["lat"]),
        longitude=float(loc["lng"]),
        components=_components(r.get("address_components", [])),
    )


async def reverse_geocode(client: GoogleMapsClient, *, lat: float, lng: float) -> Place:
    body = await client.get(
        "/geocode/json",
        {"latlng": f"{lat},{lng}"},
    )
    if body.get("status") == "ZERO_RESULTS" or not body.get("results"):
        raise GoogleMapsError(f"no reverse geocode for {lat},{lng}")
    r = body["results"][0]
    loc = r["geometry"]["location"]
    return Place(
        place_id=r.get("place_id", ""),
        formatted_address=r.get("formatted_address", ""),
        latitude=float(loc["lat"]),
        longitude=float(loc["lng"]),
        components=_components(r.get("address_components", [])),
    )
```

- [ ] **Step 4: Run tests; expect pass**

```bash
uv run pytest tests/test_google_maps_client.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/core/google_maps.py backend/app/tests/test_google_maps_client.py
git commit -m "feat(core): add async google maps client (autocomplete/details/reverse)"
```

---

### Task 12: Geo router — autocomplete, place, reverse, serviceability endpoints

**Files:**
- Create: `backend/app/src/app/api/geo.py`
- Modify: `backend/app/src/app/api/__init__.py`
- Create: `backend/app/src/app/schemas/geo.py`
- Create: `backend/app/tests/test_geo_endpoints.py`

- [ ] **Step 1: Write failing tests for the four endpoints (mock the GoogleMapsClient via dependency override)**

```python
"""Tests for /api/v1/geo/* endpoints."""
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import geo as geo_router
from app.core.google_maps import GoogleMapsClient, Place, Prediction


class _StubClient:
    def __init__(self, **calls: Any) -> None:
        self._calls = calls

    async def aclose(self) -> None: ...


async def _stub_autocomplete(client: Any, *, query: str, session_token: str) -> list[Prediction]:
    return [Prediction(place_id="p1", description=f"{query}, India")]


async def _stub_place_details(client: Any, *, place_id: str, session_token: str) -> Place:
    return Place(
        place_id=place_id,
        formatted_address="X",
        latitude=18.9, longitude=72.8,
        components=(),
    )


async def _stub_reverse(client: Any, *, lat: float, lng: float) -> Place:
    return Place(
        place_id="p2",
        formatted_address="Y",
        latitude=lat, longitude=lng,
        components=(),
    )


@pytest.fixture
def patched_geo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(geo_router, "_get_client", lambda: _StubClient())
    monkeypatch.setattr(geo_router, "autocomplete", _stub_autocomplete)
    monkeypatch.setattr(geo_router, "place_details", _stub_place_details)
    monkeypatch.setattr(geo_router, "reverse_geocode", _stub_reverse)


def test_autocomplete_returns_predictions(client: TestClient, patched_geo: None) -> None:
    r = client.get("/api/v1/geo/autocomplete", params={"q": "andheri", "session_token": "s1"})
    assert r.status_code == 200
    body = r.json()
    assert body["predictions"][0]["place_id"] == "p1"


def test_place_details_returns_lat_lng(client: TestClient, patched_geo: None) -> None:
    r = client.get("/api/v1/geo/place/p1", params={"session_token": "s1"})
    assert r.status_code == 200
    body = r.json()
    assert body["latitude"] == 18.9
    assert body["longitude"] == 72.8


def test_reverse_returns_formatted_address(client: TestClient, patched_geo: None) -> None:
    r = client.get("/api/v1/geo/reverse", params={"lat": 18.9, "lng": 72.8})
    assert r.status_code == 200
    body = r.json()
    assert body["formatted_address"] == "Y"


def test_serviceability_global_returns_count(client: TestClient) -> None:
    # No stubbing of google maps — only PostGIS query.
    r = client.post("/api/v1/geo/serviceability", json={"lat": 18.9, "lng": 72.8})
    assert r.status_code == 200
    body = r.json()
    assert "serviceable" in body
    assert "store_count" in body


def test_serviceability_per_store(client: TestClient) -> None:
    r = client.post(
        "/api/v1/geo/serviceability",
        json={"lat": 18.9, "lng": 72.8, "store_id": 99999},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["serviceable"] is False  # store doesn't exist => not serviceable
```

> **Note:** the `client` fixture is the existing one in `tests/conftest.py`. If it's not module-scope, adjust import path.

- [ ] **Step 2: Run; expect import error**

```bash
cd backend/app
uv run pytest tests/test_geo_endpoints.py -v
```

Expected: failures because `app.api.geo` doesn't exist.

- [ ] **Step 3: Define schemas in `backend/app/src/app/schemas/geo.py`**

```python
from typing import List, Optional

from pydantic import BaseModel, Field


class GeoComponent(BaseModel):
    long_name: str
    short_name: str
    types: List[str]


class GeoPrediction(BaseModel):
    place_id: str
    description: str


class GeoPlace(BaseModel):
    place_id: str
    formatted_address: str
    latitude: float
    longitude: float
    components: List[GeoComponent] = []


class AutocompleteResponse(BaseModel):
    predictions: List[GeoPrediction]


class ServiceabilityRequest(BaseModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lng: float = Field(ge=-180.0, le=180.0)
    store_id: Optional[int] = None


class ServiceabilityResponse(BaseModel):
    serviceable: bool
    store_count: Optional[int] = None
```

- [ ] **Step 4: Implement the router in `backend/app/src/app/api/geo.py`**

```python
"""Geo proxy + serviceability endpoints. All public (no auth)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.google_maps import (
    GoogleMapsClient,
    GoogleMapsError,
    autocomplete,
    place_details,
    reverse_geocode,
)
from app.db.session import get_db_session
from app.schemas.geo import (
    AutocompleteResponse,
    GeoComponent,
    GeoPlace,
    GeoPrediction,
    ServiceabilityRequest,
    ServiceabilityResponse,
)


router = APIRouter(prefix="/geo", tags=["geo"])


def _get_client() -> GoogleMapsClient:
    if not settings.GOOGLE_MAPS_SERVER_API_KEY:
        raise HTTPException(status_code=503, detail="geo provider not configured")
    return GoogleMapsClient(api_key=settings.GOOGLE_MAPS_SERVER_API_KEY)


def _to_geo_place(p) -> GeoPlace:
    return GeoPlace(
        place_id=p.place_id,
        formatted_address=p.formatted_address,
        latitude=p.latitude,
        longitude=p.longitude,
        components=[
            GeoComponent(
                long_name=c.long_name,
                short_name=c.short_name,
                types=list(c.types),
            )
            for c in p.components
        ],
    )


@router.get("/autocomplete", response_model=AutocompleteResponse)
async def autocomplete_endpoint(
    q: str = Query(min_length=1, max_length=200),
    session_token: str = Query(min_length=1, max_length=64),
) -> AutocompleteResponse:
    client = _get_client()
    try:
        preds = await autocomplete(client, query=q, session_token=session_token)
    except GoogleMapsError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        await client.aclose()
    return AutocompleteResponse(
        predictions=[GeoPrediction(place_id=p.place_id, description=p.description) for p in preds]
    )


@router.get("/place/{place_id}", response_model=GeoPlace)
async def place_endpoint(
    place_id: str,
    session_token: str = Query(min_length=1, max_length=64),
) -> GeoPlace:
    client = _get_client()
    try:
        place = await place_details(client, place_id=place_id, session_token=session_token)
    except GoogleMapsError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        await client.aclose()
    return _to_geo_place(place)


@router.get("/reverse", response_model=GeoPlace)
async def reverse_endpoint(
    lat: float = Query(ge=-90.0, le=90.0),
    lng: float = Query(ge=-180.0, le=180.0),
) -> GeoPlace:
    client = _get_client()
    try:
        place = await reverse_geocode(client, lat=lat, lng=lng)
    except GoogleMapsError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        await client.aclose()
    return _to_geo_place(place)


@router.post("/serviceability", response_model=ServiceabilityResponse)
async def serviceability_endpoint(
    body: ServiceabilityRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ServiceabilityResponse:
    point_sql = "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography"
    if body.store_id is not None:
        sql = text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM store s "
            "  JOIN address a ON a.id = s.address_id "
            f" WHERE s.id = :store_id AND s.is_active AND a.geo IS NOT NULL "
            f"   AND ST_DWithin(a.geo, {point_sql}, s.delivery_radius_km * 1000)"
            ") AS ok"
        )
        result = await session.exec(
            sql.bindparams(lat=body.lat, lng=body.lng, store_id=body.store_id)
        )
        ok = bool(result.scalar_one())
        return ServiceabilityResponse(serviceable=ok)

    sql = text(
        "SELECT COUNT(*) FROM store s "
        "JOIN address a ON a.id = s.address_id "
        f"WHERE s.is_active AND a.geo IS NOT NULL "
        f"  AND ST_DWithin(a.geo, {point_sql}, s.delivery_radius_km * 1000)"
    )
    result = await session.exec(sql.bindparams(lat=body.lat, lng=body.lng))
    count = int(result.scalar_one())
    return ServiceabilityResponse(serviceable=count > 0, store_count=count)
```

- [ ] **Step 5: Mount the router**

In `backend/app/src/app/api/__init__.py`, add:

```python
from app.api import geo

api_router.include_router(geo.router)
```

- [ ] **Step 6: Run geo endpoint tests; expect pass**

```bash
uv run pytest tests/test_geo_endpoints.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/src/app/api/geo.py backend/app/src/app/api/__init__.py \
        backend/app/src/app/schemas/geo.py backend/app/tests/test_geo_endpoints.py
git commit -m "feat(api): add /api/v1/geo/* (autocomplete, place, reverse, serviceability)"
```

---

### Task 13: Redis cache + per-IP rate limit on /geo/*

**Files:**
- Modify: `backend/app/src/app/api/geo.py`
- Modify: `backend/app/tests/test_geo_endpoints.py`

- [ ] **Step 1: Look at the existing rate-limit pattern**

Read `backend/app/src/app/core/rate_limit.py` to learn the existing token-bucket / per-identifier helper. Apply the same primitive keyed by client IP for `/geo/*`.

- [ ] **Step 2: Add Redis-backed cache helpers**

In `backend/app/src/app/api/geo.py`, before the route handlers:

```python
import json
from app.core.redis import get_redis  # existing helper


async def _cached_get(cache_key: str, ttl: int):
    redis = await get_redis()
    raw = await redis.get(cache_key)
    return json.loads(raw) if raw else None


async def _cache_set(cache_key: str, value: dict, ttl: int) -> None:
    redis = await get_redis()
    await redis.setex(cache_key, ttl, json.dumps(value))
```

- [ ] **Step 3: Wrap autocomplete + reverse handlers with cache**

```python
# autocomplete
cache_key = f"geo:auto:{session_token}:{q.lower().strip()}"
cached = await _cached_get(cache_key, settings.GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS)
if cached:
    return AutocompleteResponse(**cached)
# ... call google ...
response = AutocompleteResponse(...)
await _cache_set(cache_key, response.model_dump(), settings.GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS)
return response


# reverse: round to 4 decimals (~11m bucket) before keying
key_lat = round(lat, 4)
key_lng = round(lng, 4)
cache_key = f"geo:rev:{key_lat}:{key_lng}"
cached = await _cached_get(cache_key, settings.GEO_REVERSE_CACHE_TTL_SECONDS)
if cached:
    return GeoPlace(**cached)
# ... call google ...
result = _to_geo_place(place)
await _cache_set(cache_key, result.model_dump(), settings.GEO_REVERSE_CACHE_TTL_SECONDS)
return result
```

- [ ] **Step 4: Add a per-IP rate-limit dependency to all four routes**

```python
from fastapi import Request

async def geo_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    # uses existing core/rate_limit primitive; throws 429 if exceeded
    from app.core.rate_limit import check_rate
    await check_rate(
        namespace="geo",
        identifier=ip,
        max_calls=settings.GEO_RATE_LIMIT_PER_MIN,
        window_seconds=60,
    )
```

Add `dependencies=[Depends(geo_rate_limit)]` on each route decorator.

> If the existing `core/rate_limit.py` doesn't expose `check_rate`, add a thin wrapper there that mirrors the OTP pattern. Keep the helper signature shown above.

- [ ] **Step 5: Add a test for rate-limit (429 after exceeding)**

Append to `tests/test_geo_endpoints.py`:

```python
def test_autocomplete_rate_limit_returns_429(
    client: TestClient, patched_geo: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings as s
    monkeypatch.setattr(s, "GEO_RATE_LIMIT_PER_MIN", 2)
    for _ in range(2):
        r = client.get(
            "/api/v1/geo/autocomplete",
            params={"q": "x", "session_token": "s"},
        )
        assert r.status_code == 200
    r = client.get("/api/v1/geo/autocomplete", params={"q": "x", "session_token": "s"})
    assert r.status_code == 429
```

- [ ] **Step 6: Run; expect pass**

```bash
uv run pytest tests/test_geo_endpoints.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/src/app/api/geo.py backend/app/tests/test_geo_endpoints.py
git commit -m "feat(geo): redis cache + per-ip rate limit on /geo/*"
```

---

## Phase 4 — Stores distance + order serviceability gate

### Task 14: StoreRead carries distance_km; GET /stores/ accepts lat/lng/sort

**Files:**
- Modify: `backend/app/src/app/schemas/stores.py`
- Modify: `backend/app/src/app/api/stores.py`
- Create: `backend/app/tests/test_stores_distance.py`

- [ ] **Step 1: Add `distance_km` to StoreRead**

In `schemas/stores.py`, add:

```python
distance_km: Optional[float] = None
```

Also add `delivery_radius_km: float` and `pin_confirmed: bool` so the seller dashboard can read them.

- [ ] **Step 2: Write the failing test**

```python
"""Tests for distance filter + sort on GET /api/v1/stores/."""
import pytest
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.profile import SellerProfile
from app.models.store import Store
from app.models.base import RoleEnum  # adjust to whatever the project uses
from tests._helpers import make_seller  # if such helper exists; else inline


@pytest.mark.asyncio
async def test_stores_sorted_by_distance(
    db_session: AsyncSession, client: TestClient
) -> None:
    # Three stores around Mumbai CST (18.9398, 72.8355).
    seeds = [
        ("Near", 18.9400, 72.8360, 5.0),    # ~50m
        ("Mid",  18.9500, 72.8500, 5.0),    # ~2km
        ("Far",  19.0760, 72.8777, 5.0),    # ~17km — outside default radius
    ]
    for name, lat, lng, radius in seeds:
        addr = Address(
            address_line1="x", city="Mumbai", state="Maharashtra",
            pincode="400001", country="India", latitude=lat, longitude=lng,
        )
        db_session.add(addr)
        await db_session.flush()
        prof = SellerProfile(...)  # adapt to existing factory
        db_session.add(prof)
        await db_session.flush()
        db_session.add(Store(
            name=name, seller_profile_id=prof.id, address_id=addr.id,
            delivery_radius_km=radius, is_active=True,
        ))
    await db_session.commit()

    r = client.get(
        "/api/v1/stores/",
        params={"lat": 18.9398, "lng": 72.8355, "sort": "distance"},
    )
    assert r.status_code == 200
    body = r.json()
    names = [s["name"] for s in body]
    # "Far" excluded by its 5km radius; "Near" then "Mid"
    assert names == ["Near", "Mid"]
    assert body[0]["distance_km"] < body[1]["distance_km"]


def test_stores_no_lat_lng_returns_all_active_without_distance(
    client: TestClient,
) -> None:
    r = client.get("/api/v1/stores/")
    assert r.status_code == 200
    for s in r.json():
        assert s.get("distance_km") is None
```

> Adapt the seed code to whatever helper the existing `tests/_helpers.py` provides for creating sellers/stores. Don't reimplement; use the existing factory if present.

- [ ] **Step 3: Run; expect failure (no distance support yet)**

```bash
cd backend/app
uv run pytest tests/test_stores_distance.py -v
```

Expected: failure on the `sort=distance` assertion.

- [ ] **Step 4: Update `stores.py` list endpoint**

In `backend/app/src/app/api/stores.py`, replace `list_stores` and `_store_read` with:

```python
from typing import Optional
from sqlalchemy import text


@router.get("/", response_model=List[StoreRead])
async def list_stores(
    skip: int = 0,
    limit: int = 100,
    lat: Optional[float] = Query(default=None, ge=-90.0, le=90.0),
    lng: Optional[float] = Query(default=None, ge=-180.0, le=180.0),
    radius_km: Optional[float] = Query(default=None, gt=0, le=100),
    sort: Optional[str] = Query(default=None, pattern="^distance$"),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(get_request_locale),
) -> List[StoreRead]:
    if lat is None or lng is None:
        stmt = (
            _store_with_relations_stmt()
            .where(Store.is_active)
            .offset(skip)
            .limit(limit)
        )
        result = await session.exec(stmt)
        return [await _store_read(session, store, lang, distance_km=None) for store in result.all()]

    point = "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography"
    radius_clause = (
        "ST_DWithin(a.geo, " + point + ", LEAST(s.delivery_radius_km, :user_cap) * 1000)"
        if radius_km is not None
        else "ST_DWithin(a.geo, " + point + ", s.delivery_radius_km * 1000)"
    )
    order_clause = "ST_Distance(a.geo, " + point + ") ASC" if sort == "distance" else "s.id ASC"
    sql = text(
        "SELECT s.id, ST_Distance(a.geo, " + point + ") / 1000.0 AS distance_km "
        "FROM store s JOIN address a ON a.id = s.address_id "
        "WHERE s.is_active AND a.geo IS NOT NULL AND " + radius_clause + " "
        "ORDER BY " + order_clause + " "
        "OFFSET :skip LIMIT :limit"
    )
    rows = (
        await session.exec(
            sql.bindparams(
                lat=lat, lng=lng, skip=skip, limit=limit,
                **({"user_cap": radius_km} if radius_km is not None else {}),
            )
        )
    ).all()
    distance_by_id = {r[0]: float(r[1]) for r in rows}
    if not distance_by_id:
        return []
    stmt = _store_with_relations_stmt().where(Store.id.in_(list(distance_by_id.keys())))
    stores_unsorted = (await session.exec(stmt)).all()
    by_id = {s.id: s for s in stores_unsorted}
    ordered = [by_id[i] for i in distance_by_id.keys()]  # preserves SQL order
    return [
        await _store_read(session, store, lang, distance_km=distance_by_id[store.id])
        for store in ordered
    ]
```

Update `_store_read` signature to accept and forward `distance_km`. Make sure it appears on `StoreRead` (added in Step 1). Same for `delivery_radius_km` and `pin_confirmed`.

- [ ] **Step 5: Run; expect pass**

```bash
uv run pytest tests/test_stores_distance.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/api/stores.py backend/app/src/app/schemas/stores.py \
        backend/app/tests/test_stores_distance.py
git commit -m "feat(stores): distance filter + sort on GET /stores/, expose delivery_radius_km/pin_confirmed/distance_km"
```

---

### Task 15: Order creation rejects out-of-radius addresses

**Files:**
- Modify: `backend/app/src/app/services/checkout.py`
- Create: `backend/app/tests/test_orders_serviceability.py`

- [ ] **Step 1: Write failing test**

```python
"""Tests that POST /api/v1/orders/ rejects out-of-radius delivery addresses."""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_order_rejected_when_address_outside_radius(
    client: TestClient, seeded_store_and_far_address  # fixture defined inline below
) -> None:
    payload = {
        "store_id": seeded_store_and_far_address.store_id,
        "customer_address_id": seeded_store_and_far_address.address_id,
        # ... other required fields per the existing OrderCreate schema ...
    }
    r = client.post("/api/v1/orders/", json=payload)
    assert r.status_code == 422
    assert "outside" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_order_succeeds_when_address_inside_radius(
    client: TestClient, seeded_store_and_near_address
) -> None:
    payload = {
        "store_id": seeded_store_and_near_address.store_id,
        "customer_address_id": seeded_store_and_near_address.address_id,
    }
    r = client.post("/api/v1/orders/", json=payload)
    assert r.status_code in {200, 201}
```

> Build the two fixtures (`seeded_store_and_far_address`, `seeded_store_and_near_address`) inline in this test file using whatever pattern the existing `tests/test_orders.py` uses for seeding stores + addresses + carts. Do NOT extract into `_helpers.py` until used by 3+ tests.

- [ ] **Step 2: Run; expect failure**

```bash
cd backend/app
uv run pytest tests/test_orders_serviceability.py -v
```

Expected: 200/201 returned for the far-address case (because the assertion isn't there yet).

- [ ] **Step 3: Add the serviceability assertion in `services/checkout.py`**

In `_resolve_address` (or whichever function loads the customer's `Address` joined with the `Store`), add a `ST_DWithin` check using a raw `text()` query right after the address is loaded but before items are reserved:

```python
from sqlalchemy import text
from fastapi import HTTPException


async def _assert_serviceable(
    session: AsyncSession, *, store_id: int, address_id: int
) -> None:
    sql = text(
        "SELECT EXISTS ("
        "  SELECT 1 FROM store s "
        "  JOIN address sa ON sa.id = s.address_id "
        "  JOIN address ca ON ca.id = :address_id "
        "  WHERE s.id = :store_id "
        "    AND sa.geo IS NOT NULL AND ca.geo IS NOT NULL "
        "    AND ST_DWithin(sa.geo, ca.geo, s.delivery_radius_km * 1000)"
        ") AS ok"
    )
    ok = bool(
        (await session.exec(sql.bindparams(store_id=store_id, address_id=address_id))).scalar_one()
    )
    if not ok:
        raise HTTPException(status_code=422, detail="Address outside store delivery area")
```

Call it inside the order-creation path after address resolution and before inventory reservation.

- [ ] **Step 4: Run; expect pass**

```bash
uv run pytest tests/test_orders_serviceability.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/services/checkout.py backend/app/tests/test_orders_serviceability.py
git commit -m "feat(orders): reject orders to addresses outside store delivery radius"
```

---

## Phase 5 — Backfill task

### Task 16: One-shot Celery task to forward-geocode legacy store addresses

**Files:**
- Modify: `backend/app/src/app/worker.py`
- Create: `backend/app/tests/test_backfill_geocode.py`

- [ ] **Step 1: Write failing test (mock GoogleMapsClient)**

```python
"""Tests for the one-shot store/business address backfill Celery task."""
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.worker import backfill_store_addresses_geocode


@pytest.mark.asyncio
async def test_backfill_only_touches_store_and_business_addresses(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Customer-only address (not linked to any store / business) -> must NOT be touched.
    customer_only = Address(
        address_line1="x", city="X", state="Maharashtra",
        pincode="400001", country="India",
    )
    db_session.add(customer_only)
    # Store address (linked via SellerProfile + Store) -> MUST be touched.
    # ... seed via test helpers ...
    await db_session.commit()

    async def fake_geocode(text: str) -> tuple[float, float]:
        return (18.9, 72.8)

    monkeypatch.setattr(
        "app.worker._forward_geocode_one", fake_geocode
    )

    backfill_store_addresses_geocode.delay()  # eager mode in tests

    await db_session.refresh(customer_only)
    assert customer_only.latitude is None  # not touched

    # Assert the store address now has lat/lng + DIGIPIN
    # ... assertions ...
```

- [ ] **Step 2: Run; expect import error**

```bash
cd backend/app
uv run pytest tests/test_backfill_geocode.py -v
```

- [ ] **Step 3: Implement the Celery task in `worker.py`**

```python
from sqlalchemy import text
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.google_maps import GoogleMapsClient, GoogleMapsError
from app.db.session import get_session_context
from app.utils.digipin import encode as digipin_encode


async def _forward_geocode_one(query: str) -> tuple[float, float] | None:
    if not settings.GOOGLE_MAPS_SERVER_API_KEY:
        return None
    client = GoogleMapsClient(api_key=settings.GOOGLE_MAPS_SERVER_API_KEY)
    try:
        body = await client.get(
            "/geocode/json", {"address": query, "components": "country:IN"}
        )
        results = body.get("results", [])
        if not results or results[0].get("partial_match", False):
            return None
        loc = results[0]["geometry"]["location"]
        return float(loc["lat"]), float(loc["lng"])
    except GoogleMapsError:
        return None
    finally:
        await client.aclose()


@celery_app.task(name="geo.backfill_store_addresses")
def backfill_store_addresses_geocode() -> dict[str, int]:
    """Forward-geocode addresses linked to Store or SellerProfile.business_address.

    Skips addresses already with lat/lng and customer-only addresses. Idempotent.
    """
    import asyncio
    return asyncio.run(_run_backfill())


async def _run_backfill() -> dict[str, int]:
    sql_select = text("""
        SELECT a.id, a.address_line1, a.city, a.state, a.pincode
        FROM address a
        WHERE a.latitude IS NULL
          AND (
            EXISTS (SELECT 1 FROM store s WHERE s.address_id = a.id)
            OR EXISTS (SELECT 1 FROM sellerprofile sp WHERE sp.business_address_id = a.id)
          )
    """)
    sql_update = text("""
        UPDATE address SET latitude = :lat, longitude = :lng,
            digipin = :digipin, location_source = 'geocoded'
        WHERE id = :id
    """)
    filled = 0
    skipped = 0
    async with get_session_context() as session:
        rows = (await session.exec(sql_select)).all()
        for row in rows:
            query = f"{row.address_line1}, {row.city}, {row.state} {row.pincode}, India"
            coords = await _forward_geocode_one(query)
            if coords is None:
                skipped += 1
                continue
            lat, lng = coords
            try:
                digipin = digipin_encode(lat, lng)
            except ValueError:
                digipin = None
            await session.exec(
                sql_update.bindparams(id=row.id, lat=lat, lng=lng, digipin=digipin)
            )
            filled += 1
            await asyncio.sleep(0.1)  # 10 req/s ceiling
        await session.commit()
    return {"filled": filled, "skipped": skipped}
```

- [ ] **Step 4: Run; expect pass**

```bash
uv run pytest tests/test_backfill_geocode.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/worker.py backend/app/tests/test_backfill_geocode.py
git commit -m "feat(worker): one-shot backfill task for store/business address geocoding"
```

---

## Phase 6 — Frontend dependency + types

### Task 17: Add `@vis.gl/react-google-maps` and env

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/.env.example`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Install the dep**

```bash
cd frontend
npm install @vis.gl/react-google-maps
```

- [ ] **Step 2: Add env example**

Append to `frontend/.env.example`:

```
NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=
```

- [ ] **Step 3: Update `frontend/src/types/index.ts`**

Add the new fields to `Address` and `Store` types:

```typescript
export type LocationSource = "manual" | "autocomplete" | "pin" | "geocoded";

export interface Address {
  // existing fields ...
  digipin?: string | null;
  place_id?: string | null;
  location_source?: LocationSource | null;
}

export interface Store {
  // existing fields ...
  delivery_radius_km: number;
  pin_confirmed: boolean;
  distance_km?: number | null;
}
```

- [ ] **Step 4: Run typecheck + build**

```bash
npm run lint
npm run build
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/.env.example frontend/src/types/index.ts
git commit -m "chore(web): add react-google-maps dep + geo type fields"
```

---

## Phase 7 — Frontend components

### Task 18: `<AddressAutocomplete>` component

**Files:**
- Create: `frontend/src/components/AddressAutocomplete.tsx`
- Create: `frontend/src/components/AddressAutocomplete.module.css`
- Create: `frontend/src/lib/geo.ts`

- [ ] **Step 1: Create the API helper**

`frontend/src/lib/geo.ts`:

```typescript
import { apiGet, apiPost } from "@/lib/api";

export interface GeoComponent {
  long_name: string;
  short_name: string;
  types: string[];
}
export interface GeoPrediction {
  place_id: string;
  description: string;
}
export interface GeoPlace {
  place_id: string;
  formatted_address: string;
  latitude: number;
  longitude: number;
  components: GeoComponent[];
}

export const newSessionToken = (): string =>
  (typeof crypto !== "undefined" && "randomUUID" in crypto)
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);

export const autocomplete = (q: string, sessionToken: string) =>
  apiGet<{ predictions: GeoPrediction[] }>(
    `/api/v1/geo/autocomplete?q=${encodeURIComponent(q)}&session_token=${sessionToken}`
  );

export const placeDetails = (placeId: string, sessionToken: string) =>
  apiGet<GeoPlace>(
    `/api/v1/geo/place/${encodeURIComponent(placeId)}?session_token=${sessionToken}`
  );

export const reverseGeocode = (lat: number, lng: number) =>
  apiGet<GeoPlace>(
    `/api/v1/geo/reverse?lat=${lat}&lng=${lng}`
  );

export const checkServiceability = (lat: number, lng: number, storeId?: number) =>
  apiPost<{ serviceable: boolean; store_count?: number }>(
    "/api/v1/geo/serviceability",
    { lat, lng, ...(storeId !== undefined ? { store_id: storeId } : {}) }
  );
```

> If `apiGet`/`apiPost` aren't the existing helpers, use the existing fetch wrapper from `frontend/src/lib/api.ts` instead. Do not create new ones.

- [ ] **Step 2: Implement the component**

```typescript
"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  autocomplete,
  newSessionToken,
  placeDetails,
  type GeoPlace,
  type GeoPrediction,
} from "@/lib/geo";
import styles from "./AddressAutocomplete.module.css";

export interface AddressAutocompleteProps {
  initialValue?: string;
  placeholder?: string;
  onPlace: (place: GeoPlace) => void;   // user picked a suggestion
  onSessionEnd?: () => void;            // optional hook called after place pick
  disabled?: boolean;
}

export function AddressAutocomplete({
  initialValue = "",
  placeholder = "Search for your address",
  onPlace,
  onSessionEnd,
  disabled,
}: AddressAutocompleteProps) {
  const [query, setQuery] = useState(initialValue);
  const [predictions, setPredictions] = useState<GeoPrediction[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessionTokenRef = useRef<string>(newSessionToken());
  const debounceRef = useRef<number | null>(null);

  useEffect(() => {
    if (!query || query.length < 3) {
      setPredictions([]);
      return;
    }
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(async () => {
      try {
        const r = await autocomplete(query, sessionTokenRef.current);
        setPredictions(r.predictions);
        setOpen(true);
        setError(null);
      } catch {
        setError("Suggestions unavailable, type address manually");
        setPredictions([]);
      }
    }, 250);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [query]);

  const pick = useCallback(
    async (p: GeoPrediction) => {
      try {
        const place = await placeDetails(p.place_id, sessionTokenRef.current);
        onPlace(place);
        setQuery(place.formatted_address);
        setOpen(false);
        sessionTokenRef.current = newSessionToken();  // billing: end session
        onSessionEnd?.();
      } catch {
        setError("Could not load address details");
      }
    },
    [onPlace, onSessionEnd]
  );

  return (
    <div className={styles.wrapper}>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className={styles.input}
      />
      {error && <div className={styles.error}>{error}</div>}
      {open && predictions.length > 0 && (
        <ul className={styles.dropdown}>
          {predictions.map((p) => (
            <li
              key={p.place_id}
              className={styles.option}
              onClick={() => pick(p)}
            >
              {p.description}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Style it (CSS Modules; reuse design tokens)**

Minimal `AddressAutocomplete.module.css`:

```css
.wrapper { position: relative; }
.input {
  width: 100%; padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-border); border-radius: var(--radius-md);
  font: inherit;
}
.dropdown {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 20;
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-md); margin-top: 4px;
  list-style: none; padding: 0; max-height: 240px; overflow-y: auto;
}
.option {
  padding: var(--space-3) var(--space-4); cursor: pointer;
}
.option:hover { background: var(--color-surface-hover); }
.error { color: var(--color-danger); font-size: var(--text-sm); margin-top: 4px; }
```

- [ ] **Step 4: Build & verify**

```bash
cd frontend
npm run lint
npm run build
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AddressAutocomplete.* frontend/src/lib/geo.ts
git commit -m "feat(web): AddressAutocomplete component + geo api helpers"
```

---

### Task 19: `<MapPicker>` component

**Files:**
- Create: `frontend/src/components/MapPicker.tsx`
- Create: `frontend/src/components/MapPicker.module.css`

- [ ] **Step 1: Implement**

```typescript
"use client";

import { useState, useCallback } from "react";
import {
  APIProvider, Map, AdvancedMarker, useMap,
} from "@vis.gl/react-google-maps";
import { reverseGeocode, type GeoPlace } from "@/lib/geo";
import styles from "./MapPicker.module.css";

export interface MapPickerProps {
  initialLat?: number;
  initialLng?: number;
  requirePin?: boolean;
  onPlace: (place: GeoPlace) => void;
  onError?: (msg: string) => void;
}

const DEFAULT_CENTER = { lat: 19.0760, lng: 72.8777 };  // Mumbai

export function MapPicker({
  initialLat, initialLng, requirePin, onPlace, onError,
}: MapPickerProps) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY ?? "";
  const [pos, setPos] = useState({
    lat: initialLat ?? DEFAULT_CENTER.lat,
    lng: initialLng ?? DEFAULT_CENTER.lng,
  });
  const [resolved, setResolved] = useState<GeoPlace | null>(null);

  const handleDragEnd = useCallback(
    async (lat: number, lng: number) => {
      setPos({ lat, lng });
      try {
        const place = await reverseGeocode(lat, lng);
        if (!place.components.some((c) => c.types.includes("country") && c.short_name === "IN")) {
          onError?.("KhanaBazaar serves India only");
          return;
        }
        setResolved(place);
        onPlace(place);
      } catch {
        onError?.("Could not resolve address from pin");
      }
    },
    [onPlace, onError]
  );

  const useMyLocation = useCallback(() => {
    if (!navigator.geolocation) {
      onError?.("Geolocation not supported");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => handleDragEnd(pos.coords.latitude, pos.coords.longitude),
      () => onError?.("Permission denied — drag pin to your location"),
    );
  }, [handleDragEnd, onError]);

  if (!apiKey) {
    return (
      <div className={styles.fallback}>
        Map unavailable. Enter address manually.
      </div>
    );
  }

  return (
    <APIProvider apiKey={apiKey}>
      <div className={styles.wrapper}>
        <button type="button" onClick={useMyLocation} className={styles.locBtn}>
          Use my location
        </button>
        <Map
          defaultCenter={pos}
          defaultZoom={16}
          mapId="kb-picker"
          onCameraChanged={(e) => {
            const c = e.detail.center;
            handleDragEnd(c.lat, c.lng);
          }}
          style={{ width: "100%", height: "320px" }}
        >
          <AdvancedMarker position={pos} draggable
            onDragEnd={(e) => {
              const ll = e.latLng;
              if (ll) handleDragEnd(ll.lat(), ll.lng());
            }}
          />
        </Map>
        <p className={styles.hint}>
          Move pin to your exact door. {requirePin && !resolved && (
            <strong>Pin location to continue.</strong>
          )}
        </p>
      </div>
    </APIProvider>
  );
}
```

- [ ] **Step 2: Style**

```css
.wrapper { display: flex; flex-direction: column; gap: var(--space-3); }
.locBtn {
  align-self: flex-start; padding: var(--space-2) var(--space-3);
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-md); cursor: pointer;
}
.hint { color: var(--color-muted); font-size: var(--text-sm); }
.fallback {
  padding: var(--space-4); border: 1px dashed var(--color-border);
  border-radius: var(--radius-md); color: var(--color-muted);
}
```

- [ ] **Step 3: Build**

```bash
cd frontend
npm run build
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/MapPicker.*
git commit -m "feat(web): MapPicker with draggable pin + reverse geocode"
```

---

### Task 20: `<DeliveryLocationContext>` + persistent storage

**Files:**
- Create: `frontend/src/lib/DeliveryLocationContext.tsx`
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Step 1: Implement context**

```typescript
"use client";

import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from "react";

export interface DeliveryLocation {
  lat: number;
  lng: number;
  label: string;
}

interface DeliveryLocationContextValue {
  location: DeliveryLocation | null;
  setLocation: (loc: DeliveryLocation | null) => void;
  clear: () => void;
}

const STORAGE_KEY = "kb_delivery_location";

const DeliveryLocationContext = createContext<DeliveryLocationContextValue | null>(null);

export function DeliveryLocationProvider({ children }: { children: React.ReactNode }) {
  const [location, setLocationState] = useState<DeliveryLocation | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setLocationState(JSON.parse(raw));
    } catch { /* ignore */ }
  }, []);

  const setLocation = useCallback((loc: DeliveryLocation | null) => {
    setLocationState(loc);
    if (loc) localStorage.setItem(STORAGE_KEY, JSON.stringify(loc));
    else localStorage.removeItem(STORAGE_KEY);
  }, []);

  const clear = useCallback(() => setLocation(null), [setLocation]);

  const value = useMemo(() => ({ location, setLocation, clear }), [location, setLocation, clear]);

  return <DeliveryLocationContext.Provider value={value}>{children}</DeliveryLocationContext.Provider>;
}

export function useDeliveryLocation(): DeliveryLocationContextValue {
  const ctx = useContext(DeliveryLocationContext);
  if (!ctx) throw new Error("useDeliveryLocation must be inside DeliveryLocationProvider");
  return ctx;
}

export function truncateLabel(text: string, max = 40): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}
```

- [ ] **Step 2: Mount the provider in `frontend/src/app/layout.tsx`**

Wrap the existing providers (`AuthProvider`, `CartProvider`) so the new provider sits inside `<AuthProvider>` (so it can read auth state if needed) but outside `<CartProvider>`:

```tsx
<AuthProvider>
  <DeliveryLocationProvider>
    <CartProvider>
      {children}
    </CartProvider>
  </DeliveryLocationProvider>
</AuthProvider>
```

- [ ] **Step 3: Build**

```bash
cd frontend
npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/DeliveryLocationContext.tsx frontend/src/app/layout.tsx
git commit -m "feat(web): DeliveryLocationContext + provider mount"
```

---

### Task 21: `<DeliveryLocationPicker>` modal

**Files:**
- Create: `frontend/src/components/DeliveryLocationPicker.tsx`
- Create: `frontend/src/components/DeliveryLocationPicker.module.css`

- [ ] **Step 1: Implement**

```typescript
"use client";

import { useState } from "react";
import { Modal } from "@/components/Modal";
import { AddressAutocomplete } from "@/components/AddressAutocomplete";
import { MapPicker } from "@/components/MapPicker";
import {
  useDeliveryLocation, truncateLabel,
} from "@/lib/DeliveryLocationContext";
import styles from "./DeliveryLocationPicker.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function DeliveryLocationPicker({ open, onClose }: Props) {
  const { setLocation } = useDeliveryLocation();
  const [stagedLat, setStagedLat] = useState<number | null>(null);
  const [stagedLng, setStagedLng] = useState<number | null>(null);
  const [stagedLabel, setStagedLabel] = useState<string>("");

  const stage = (lat: number, lng: number, label: string) => {
    setStagedLat(lat);
    setStagedLng(lng);
    setStagedLabel(label);
  };

  const confirm = () => {
    if (stagedLat == null || stagedLng == null) return;
    setLocation({ lat: stagedLat, lng: stagedLng, label: truncateLabel(stagedLabel) });
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title="Set delivery location">
      <div className={styles.body}>
        <AddressAutocomplete
          onPlace={(p) => stage(p.latitude, p.longitude, p.formatted_address)}
        />
        <p className={styles.or}>or pin on map</p>
        <MapPicker
          initialLat={stagedLat ?? undefined}
          initialLng={stagedLng ?? undefined}
          onPlace={(p) => stage(p.latitude, p.longitude, p.formatted_address)}
        />
        <button
          type="button"
          className={styles.confirm}
          onClick={confirm}
          disabled={stagedLat == null}
        >
          Confirm location
        </button>
      </div>
    </Modal>
  );
}
```

- [ ] **Step 2: Style + build + commit**

```css
.body { display: flex; flex-direction: column; gap: var(--space-4); }
.or { text-align: center; color: var(--color-muted); }
.confirm {
  padding: var(--space-3) var(--space-4); background: var(--color-primary);
  color: white; border: 0; border-radius: var(--radius-md);
}
.confirm:disabled { opacity: 0.5; cursor: not-allowed; }
```

```bash
cd frontend && npm run build
git add frontend/src/components/DeliveryLocationPicker.*
git commit -m "feat(web): DeliveryLocationPicker modal (autocomplete + map)"
```

---

### Task 22: Update `<AddressFields>` with autocomplete + map

**Files:**
- Modify: `frontend/src/components/AddressFields.tsx`
- Modify: `frontend/src/components/AddressFields.module.css`

- [ ] **Step 1: Add `<AddressAutocomplete>` above line1 and a togglable `<MapPicker>`**

Patch `AddressFields.tsx`:

```tsx
import { AddressAutocomplete } from "@/components/AddressAutocomplete";
import { MapPicker } from "@/components/MapPicker";
import type { GeoComponent, GeoPlace } from "@/lib/geo";

export interface AddressFieldsProps {
  value: Address;
  onChange: (next: Address) => void;
  errors?: AddressFieldsErrors;
  disabled?: boolean;
  requirePin?: boolean;  // seller signup uses true
}

function applyPlaceToAddress(place: GeoPlace, current: Address): Address {
  const get = (type: string): string =>
    place.components.find((c) => c.types.includes(type))?.long_name ?? "";
  return {
    ...current,
    address_line1: place.formatted_address.split(",")[0] || current.address_line1,
    city: get("locality") || get("administrative_area_level_2") || current.city,
    state: get("administrative_area_level_1") || current.state,
    pincode: get("postal_code") || current.pincode,
    country: get("country") || current.country,
    latitude: place.latitude,
    longitude: place.longitude,
    place_id: place.place_id,
    location_source: "autocomplete",  // overridden to 'pin' if MapPicker is used last
  };
}

export function AddressFields({
  value, onChange, errors, disabled, requirePin = false,
}: AddressFieldsProps) {
  const [showMap, setShowMap] = useState(requirePin);

  const handleAutocomplete = (place: GeoPlace) =>
    onChange(applyPlaceToAddress(place, value));

  const handlePinDrop = (place: GeoPlace) =>
    onChange({ ...applyPlaceToAddress(place, value), location_source: "pin" });

  return (
    <div className={styles.grid}>
      <div className={`${styles.field} ${styles.span2}`}>
        <AddressAutocomplete
          initialValue={value.address_line1}
          onPlace={handleAutocomplete}
          disabled={disabled}
        />
      </div>
      {/* ... existing line1/line2/city/state/pincode fields unchanged ... */}

      <div className={`${styles.field} ${styles.span2}`}>
        {!showMap && !requirePin && (
          <button type="button" className={styles.toggle} onClick={() => setShowMap(true)}>
            Pin location for accurate delivery
          </button>
        )}
        {showMap && (
          <MapPicker
            initialLat={value.latitude ?? undefined}
            initialLng={value.longitude ?? undefined}
            requirePin={requirePin}
            onPlace={handlePinDrop}
          />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build & commit**

```bash
cd frontend && npm run build
git add frontend/src/components/AddressFields.*
git commit -m "feat(web): AddressFields integrates autocomplete + map picker"
```

---

### Task 23: `<StoreCardWithDistance>` + store list integration

**Files:**
- Modify: `frontend/src/components/ProductCard.tsx` if a store-card lives there, else create `frontend/src/components/StoreCard.tsx`
- Modify: `frontend/src/app/(customer)/[locale]/stores/page.tsx`

> Inspect first which file currently renders the store list. Reuse / patch it; do not duplicate.

- [ ] **Step 1: Add a `distance_km` badge to the existing store card**

```tsx
{typeof store.distance_km === "number" && (
  <span className={styles.distanceBadge}>{store.distance_km.toFixed(1)} km</span>
)}
```

- [ ] **Step 2: Wire the store-list page (`(customer)/[locale]/stores/page.tsx`) AND the home page (`(customer)/[locale]/page.tsx`) to the delivery location**

Both pages render store lists. Apply the same change to both:

```tsx
const { location } = useDeliveryLocation();
const url = location
  ? `/api/v1/stores/?lat=${location.lat}&lng=${location.lng}&sort=distance`
  : `/api/v1/stores/`;
```

Render an empty state when zero stores returned and a location is set:

```tsx
if (location && stores.length === 0) {
  return <div>No stores deliver here yet.</div>;
}
```

- [ ] **Step 3: Build, manual smoke test, commit**

```bash
cd frontend && npm run build
git add frontend/src/components/* frontend/src/app/\(customer\)/\[locale\]/stores/*
git commit -m "feat(web): show store distance + filter by user location"
```

---

### Task 24: Navbar "Deliver to" chip + open the picker

**Files:**
- Modify: `frontend/src/components/Navbar.tsx`
- Modify: `frontend/src/components/Navbar.module.css`

- [ ] **Step 1: Add chip + modal**

```tsx
import { useState } from "react";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { DeliveryLocationPicker } from "@/components/DeliveryLocationPicker";

const { location } = useDeliveryLocation();
const [pickerOpen, setPickerOpen] = useState(false);
// Inside the navbar JSX:
<button
  type="button"
  className={styles.deliverChip}
  onClick={() => setPickerOpen(true)}
>
  📍 {location?.label ?? "Set location"}
</button>
<DeliveryLocationPicker open={pickerOpen} onClose={() => setPickerOpen(false)} />
```

- [ ] **Step 2: Style chip + commit**

```css
.deliverChip {
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-pill); cursor: pointer;
}
```

```bash
cd frontend && npm run build
git add frontend/src/components/Navbar.*
git commit -m "feat(web): navbar 'Deliver to' chip opens location picker"
```

---

### Task 25: Checkout serviceability gate

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/checkout/[storeId]/page.tsx`

- [ ] **Step 1: For each saved address, call `/geo/serviceability` with `store_id` and disable un-serviceable rows**

```tsx
import { checkServiceability } from "@/lib/geo";

const [serviceability, setServiceability] = useState<Record<number, boolean>>({});

useEffect(() => {
  (async () => {
    const map: Record<number, boolean> = {};
    for (const a of addresses) {
      if (a.latitude == null || a.longitude == null) {
        map[a.id] = false;
        continue;
      }
      try {
        const r = await checkServiceability(a.latitude, a.longitude, storeId);
        map[a.id] = r.serviceable;
      } catch {
        map[a.id] = false;
      }
    }
    setServiceability(map);
  })();
}, [addresses, storeId]);

// In the address dropdown:
<option key={a.id} value={a.id} disabled={!serviceability[a.id]}>
  {format(a)} {!serviceability[a.id] && "(Outside delivery area)"}
</option>
```

- [ ] **Step 2: Build & commit**

```bash
cd frontend && npm run build
git add frontend/src/app/\(customer\)/\[locale\]/checkout/\[storeId\]/page.tsx
git commit -m "feat(web): disable un-serviceable addresses in checkout"
```

---

### Task 26: Seller signup wizard map step

**Files:**
- Modify: `frontend/src/app/(operator)/seller/signup/page.tsx`

- [ ] **Step 1: Pass `requirePin={true}` to AddressFields and block Next until lat/lng set**

```tsx
<AddressFields
  value={address}
  onChange={setAddress}
  requirePin
/>

<button
  type="button"
  disabled={address.latitude == null || address.longitude == null}
  onClick={next}
>
  Next
</button>
```

- [ ] **Step 2: When submitting the final register payload, also set `pin_confirmed=true` on the store create call.**

In the seller-register API call body, include `pin_confirmed: true` for the new store. Backend store-create endpoint must accept this — Task 8 schema covers it; verify the create handler reads it from payload.

- [ ] **Step 3: Build, manual flow check, commit**

```bash
cd frontend && npm run build
git add frontend/src/app/\(operator\)/seller/signup/page.tsx
git commit -m "feat(web): seller signup forces pin drop, sends pin_confirmed=true"
```

---

### Task 27: Seller dashboard — radius slider + pin banner

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/page.tsx` (or wherever the seller dashboard root is)

- [ ] **Step 1: Show banner when `pin_confirmed === false`**

```tsx
{store && !store.pin_confirmed && (
  <div className={styles.banner}>
    <strong>Confirm your store pin.</strong> Customers can't find you on the map yet.
    <button onClick={openPinEditor}>Confirm now</button>
  </div>
)}
```

- [ ] **Step 2: Add a slider that PATCHes `delivery_radius_km` (0.5–50)**

```tsx
<label>
  Delivery radius: {store.delivery_radius_km.toFixed(1)} km
  <input
    type="range" min={0.5} max={50} step={0.5}
    value={store.delivery_radius_km}
    onChange={(e) => updateRadius(parseFloat(e.target.value))}
  />
</label>
```

`updateRadius` calls the existing store-update endpoint (PATCH or PUT — match the backend route).

- [ ] **Step 3: Build + commit**

```bash
cd frontend && npm run build
git add frontend/src/app/\(operator\)/seller/*
git commit -m "feat(web): seller dashboard exposes radius slider + pin-confirm banner"
```

---

### Task 28: Clear `kb_delivery_location` on logout

**Files:**
- Modify: `frontend/src/lib/AuthContext.tsx`

- [ ] **Step 1: Patch `logout`**

```tsx
const logout = useCallback(() => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem("kb_delivery_location");  // prevent leaking guest pick
  setToken(null);
  setDbUser(null);
}, []);
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/AuthContext.tsx
git commit -m "fix(web): clear delivery location on logout to avoid cross-user leak"
```

---

## Phase 8 — Docs + Azure infra notes

### Task 29: Update CLAUDE.md, development_guide, azure_deployment

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/development_guide.md`
- Modify: `docs/azure_deployment.md`
- Modify: `docs/flows.md`

- [ ] **Step 1: Add a "Geo / distance / PostGIS" section to `docs/development_guide.md`**

Document:
- PostGIS extension required locally (image swap done in Task 1).
- DIGIPIN module location + algorithm reference.
- `/geo/*` endpoints and their session-token / cache / rate-limit behavior.
- How tests mock the Google client (the global stub from Task 11).

- [ ] **Step 2: Add a flow section to `docs/flows.md`**

Document:
- Guest delivery-location flow.
- Customer add-address flow with autocomplete + pin.
- Checkout serviceability gate.
- Seller signup pin step.

- [ ] **Step 3: Update `docs/azure_deployment.md`**

Add:
- PostGIS server-parameter requirement: set `azure.extensions` to include `POSTGIS` in the Bicep `azure-postgresql-server.bicep` module.
- Two new Key Vault secrets: `GOOGLE_MAPS_SERVER_API_KEY` (server, IP-restricted) and `GOOGLE_MAPS_BROWSER_API_KEY` (referrer-restricted).

- [ ] **Step 4: Update `CLAUDE.md`**

Under "Non-obvious patterns / gotchas", add a short "Geo + PostGIS" subsection mirroring the spec essentials. Keep it brief — point to the spec/plan for detail.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/
git commit -m "docs: geo + postgis + maps key requirements across guides"
```

---

### Task 30: Bicep infra — enable POSTGIS extension on Azure Postgres Flexible Server

**Files:**
- Modify: `infra/<postgres>.bicep` (whichever module provisions the Postgres server)

- [ ] **Step 1: Find the Postgres module**

```bash
grep -rn "Microsoft.DBforPostgreSQL" infra/
```

- [ ] **Step 2: Add the `azure.extensions` server parameter**

In the matching `Microsoft.DBforPostgreSQL/flexibleServers/configurations` resource block (or create one), set value to a comma-separated list including `POSTGIS`:

```bicep
resource postgisExtension 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-03-01-preview' = {
  parent: postgresServer
  name: 'azure.extensions'
  properties: {
    value: 'POSTGIS'
    source: 'user-override'
  }
}
```

- [ ] **Step 3: Add the two Google Maps keys to Key Vault module + container app envFrom**

Append:

```bicep
resource googleServerKey 'Microsoft.KeyVault/vaults/secrets@...' = {
  parent: keyVault
  name: 'google-maps-server-api-key'
  properties: { value: '' }  // populated post-deploy via az cli
}
```

(Same for `google-maps-browser-api-key`.) Wire both into the FastAPI container app via `secretRef`. Wire the browser key as a build-time env var for the Next.js container app (`NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`).

- [ ] **Step 4: Commit (do not deploy from plan; deployment is human-driven)**

```bash
git add infra/
git commit -m "infra(azure): enable POSTGIS extension + google maps key vault secrets"
```

---

## Phase 9 — Final verification

### Task 31: Full backend test suite + lint

- [ ] **Step 1: Run everything**

```bash
cd backend/app
uv run pytest -v
uv run ruff check .
uv run mypy .
```

Expected: all green.

- [ ] **Step 2: Frontend lint + build**

```bash
cd frontend
npm run lint
npm run build
```

Expected: clean.

### Task 32: Open PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin feat/geo-stores-delivery-radius
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --title "feat: geo-aware stores, delivery radius, address mapping" --body "$(cat <<'EOF'
## Summary
- PostGIS-backed distance sort + per-store delivery radius (`ST_DWithin` / `ST_Distance`)
- Google Maps autocomplete + map pin via backend proxy (`/api/v1/geo/*`)
- DIGIPIN auto-derived server-side on every address write
- Order creation gated by serviceability; checkout UI disables un-serviceable addresses
- Seller signup forces pin drop; existing stores backfilled by Celery task

## Test plan
- [ ] `uv run pytest -v` (backend)
- [ ] `npm run lint && npm run build` (frontend)
- [ ] Manual: guest sets location, sees stores sorted by distance; far stores excluded
- [ ] Manual: logged-in user picks a saved address outside store radius → checkout blocks
- [ ] Manual: seller signup blocks until pin placed; pin_confirmed banner clears
EOF
)"
```

---

## Self-review checklist

Run this against the spec one last time:

- [ ] PostGIS extension enabled (Tasks 1, 2, 6, 30)
- [ ] DIGIPIN module + tests (Tasks 3, 4, 5)
- [ ] `Address` schema additions: `digipin`, `place_id`, `location_source`, `geo` generated column (Task 7)
- [ ] `Store` schema additions: `delivery_radius_km`, `pin_confirmed` (Task 8)
- [ ] `address_from_payload` derives DIGIPIN (Task 9)
- [ ] Google Maps client (Task 11)
- [ ] `/geo/autocomplete`, `/geo/place/{id}`, `/geo/reverse`, `/geo/serviceability` (Task 12)
- [ ] Per-IP rate limit + Redis cache on `/geo/*` (Task 13)
- [ ] `GET /stores/` distance filter/sort + `distance_km` in response (Task 14)
- [ ] `POST /orders/` serviceability assertion (Task 15)
- [ ] Backfill task (store + business addresses only) (Task 16)
- [ ] React Google Maps dep + types (Task 17)
- [ ] `<AddressAutocomplete>` (Task 18) — session token regenerated after `placeDetails`
- [ ] `<MapPicker>` (Task 19) — `requirePin` prop, India-only guard
- [ ] `<DeliveryLocationContext>` (Task 20) — `label` truncated, persisted
- [ ] `<DeliveryLocationPicker>` modal (Task 21)
- [ ] `<AddressFields>` integrates autocomplete + map (Task 22)
- [ ] Store-card distance badge + store list integration (Task 23)
- [ ] Navbar chip (Task 24)
- [ ] Checkout serviceability gate using per-store check (Task 25)
- [ ] Seller signup `requirePin=true` + `pin_confirmed=true` write (Task 26)
- [ ] Seller dashboard radius slider + banner (Task 27)
- [ ] Auth logout clears `kb_delivery_location` (Task 28)
- [ ] Docs updated incl. PostGIS + maps keys + Bicep (Tasks 29, 30)
