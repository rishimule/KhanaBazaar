# Shop-by-Service Stores Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the home page "Shop by service" tiles route into a service-filtered store list, and make a click on any store there land on that service's section of the store detail page.

**Architecture:** Backend adds a `?service=<slug>` query parameter to `GET /api/v1/stores/` that filters by `SellerProfileService` junction membership; sort behavior is unchanged. The home tile `href` switches from `/stores` to `/stores?service=<slug>`. The stores list page reads the slug from `useSearchParams`, builds a filtered fetch URL, renders a header chip with a Clear link, and embeds the service id into each store card's link. The store detail page reads `?service=<id>` once on mount, seeds `activeServiceId` (and `activeCategoryId` from the matched service's first category), and calls `router.replace` to drop the param. When the requested service is offered by the seller but has no in-stock inventory (so it does not appear in `storefront.services`), the store page renders a per-service empty state instead of silently falling back to another tab.

**Tech Stack:** FastAPI 0.135 + SQLModel (asyncpg) for the backend filter, Next.js 16 App Router + React 19 + next-intl 4 + `useSearchParams` / `useRouter` from `next/navigation` for the frontend. Backend test harness uses real Postgres (`khanabazaar_test`) via `pytest-asyncio` + `httpx.AsyncClient`. No new dependencies, no schema changes.

**Spec:** `docs/superpowers/specs/2026-05-14-shop-by-service-stores-design.md`

---

## File Structure

Files this plan creates or modifies:

- **Modify** `backend/app/src/app/api/stores.py` — extend `list_stores` with an optional `service` slug query param. The handler stays in one place; both the no-location ORM branch and the lat/lng raw-SQL branch acquire a junction-membership filter. No new file.
- **Modify** `backend/app/tests/test_stores.py` — append five integration tests covering the new filter (positive, unknown slug, inactive service slug, stockless offering, lat/lng distance sort).
- **Modify** `frontend/src/app/(customer)/[locale]/page.tsx` — change tile `href` from `/stores` to `/stores?service=${s.slug}` (line ~104 of the existing file).
- **Modify** `frontend/src/app/(customer)/[locale]/stores/page.tsx` — split the existing default export into a small wrapper that provides a `<Suspense>` boundary plus an inner client component that reads `useSearchParams`, applies the slug filter, renders the header chip / Clear link / empty state, and links each store card to `/stores/<id>?service=<service_id>`. Also fetches `/api/v1/catalog/services` once to resolve slug → localized name for the chip.
- **Modify** `frontend/src/app/(customer)/[locale]/stores/page.module.css` — add styles for `filteredChip`, `filteredChipLabel`, `filteredChipClear`.
- **Modify** `frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx` — read `?service=<id>` once via a ref-guarded effect, seed `activeServiceId` / `activeCategoryId`, call `router.replace` to drop the param, and add a per-service empty state branch when the requested service is in `store.services` but not in `storefront.services`.
- **Modify** `frontend/messages/{en,hi,mr,gu,pa}.json` — append translation keys under `Stores` (`filteredHeader`, `clearFilter`, `emptyNoLocation`, `emptyWithLocation`) and `StoreDetail` (`noProductsForService`).

No new files. No backend migrations.

---

## Task 1: Backend — add `?service=<slug>` filter to `GET /stores/`

**Files:**
- Modify: `backend/app/src/app/api/stores.py:108-176`
- Test: `backend/app/tests/test_stores.py` (append five tests at end of file)

### Background the engineer needs

- `Service` rows have a unique `slug` (e.g. `"grocery"`, `"pharmacy"`) and an `is_active` flag.
- `SellerProfileService` (table `sellerprofile_service`, class `app.models.profile.SellerProfileService`) is the junction between `SellerProfile.id` and `Service.id`. A row's presence means the seller offers that service. There is no per-row active flag — the only "active" signal is `Service.is_active`.
- `Store.seller_profile_id` is the link from a store back to its seller profile.
- The current `list_stores` handler has two branches:
  - No `lat`+`lng`: builds a SQLModel `select(Store)` statement.
  - `lat`+`lng` provided: runs a raw `text(...)` SQL against the `store` + `address` tables for distance computation, then re-fetches the store rows with relations.
- The filter must apply in both branches so behavior is identical.
- The autouse fixture in `tests/test_stores.py` already seeds one `Service(slug="grocery")` with `SellerProfileService(seller_profile_id=<seed>, service_id=<grocery>)`. New tests can seed extra `Service` rows, extra `User`/`SellerProfile` rows, extra `Address` rows, and extra `Store` rows directly via the `session` fixture. Note: each `SellerProfile` may own only **one** `Store` (DB unique constraint surfaced as HTTP 409 in `create_store`); to test multi-store scenarios, create one seller profile per store.
- The tests use `httpx.AsyncClient` + `ASGITransport(app=app)`. Catalog reads are public, so no auth override is needed for `GET /stores/`.

### Implementation outline

Add `service: Optional[str] = Query(default=None, max_length=64)` to the signature. After the parameter is read:

1. If `service` is provided, resolve it: `SELECT id FROM service WHERE slug = :slug AND is_active = true LIMIT 1`. If no row, raise `HTTPException(status_code=400, detail="unknown_service")`.
2. Use the resolved id in both branches:
   - **No-location branch:** chain `.where(Store.seller_profile_id.in_(select(SellerProfileService.seller_profile_id).where(SellerProfileService.service_id == service_id)))` onto the existing statement.
   - **Lat/lng branch:** extend the raw SQL `WHERE` clause with `AND EXISTS (SELECT 1 FROM sellerprofile_service sps WHERE sps.seller_profile_id = s.seller_profile_id AND sps.service_id = :service_id)`, and pass `service_id` in `bind_params`.

The `is_active` filter on `Service` is enforced at slug-resolution time, so the membership filter does not need to re-check it.

### Steps

- [ ] **Step 1: Write the five failing tests**

Append the following to `backend/app/tests/test_stores.py` (the file already imports `Service`, `ServiceTranslation`, `SellerProfile`, `SellerProfileService`, `Address`, `User`, `UserRole`, `VerificationStatus`, `select`, `AsyncSession`, `pytest`, `AsyncClient`, `ASGITransport`, `app`, `make_address`). Add the missing `from app.models.store import Store` import at the top of the file if it isn't already there.

```python
async def _seed_second_seller_with_services(
    session: AsyncSession,
    *,
    email: str,
    service_slugs: list[str],
    address_overrides: dict[str, object] | None = None,
) -> int:
    """Create a fresh user + seller profile, attach the given services, return the seller_profile_id.

    Each test that needs more than one store creates a new (user, profile) pair
    because the unique constraint on Store.seller_profile_id allows only one
    store per profile.
    """
    new_user = User(email=email, role=UserRole.Seller, is_active=True)
    session.add(new_user)
    await session.flush()
    assert new_user.id is not None

    addr = Address(**make_address(**(address_overrides or {})))
    session.add(addr)
    await session.flush()
    assert addr.id is not None

    profile = SellerProfile(
        user_id=new_user.id,
        first_name="Seller",
        last_name=None,
        business_name=f"Biz {email}",
        phone="+919800000000",
        gst_number="06AAAAA1111A1Z1",
        fssai_license="44556677889900",
        bank_account_number="80100200300700",
        bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(profile)
    await session.flush()
    assert profile.id is not None

    for slug in service_slugs:
        row = await session.exec(select(Service).where(Service.slug == slug))
        svc = row.first()
        if svc is None:
            svc = Service(slug=slug)
            session.add(svc)
            await session.flush()
            assert svc.id is not None
            session.add(
                ServiceTranslation(
                    service_id=svc.id, language_code="en", name=slug.title()
                )
            )
            await session.flush()
        assert svc.id is not None
        session.add(
            SellerProfileService(seller_profile_id=profile.id, service_id=svc.id)
        )
    await session.commit()
    return profile.id


async def _create_store_for_profile(
    session: AsyncSession,
    *,
    seller_profile_id: int,
    name: str,
    address_overrides: dict[str, object] | None = None,
    delivery_radius_km: float = 100.0,
) -> int:
    addr = Address(**make_address(**(address_overrides or {})))
    session.add(addr)
    await session.flush()
    assert addr.id is not None
    store = Store(
        name=name,
        seller_profile_id=seller_profile_id,
        address_id=addr.id,
        delivery_radius_km=delivery_radius_km,
    )
    session.add(store)
    await session.commit()
    assert store.id is not None
    return store.id


@pytest.mark.asyncio
async def test_list_stores_filter_by_service(session: AsyncSession) -> None:
    # autouse fixture already created Seller A (grocery). Add Seller B (pharmacy).
    seller_a_profile_row = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == mock_seller.id)
    )
    seller_a = seller_a_profile_row.first()
    assert seller_a is not None and seller_a.id is not None
    await _create_store_for_profile(
        session, seller_profile_id=seller_a.id, name="Grocery Store"
    )

    seller_b_id = await _seed_second_seller_with_services(
        session, email="pharma@kb.com", service_slugs=["pharmacy"]
    )
    await _create_store_for_profile(
        session, seller_profile_id=seller_b_id, name="Pharma Mart",
        address_overrides={"pincode": "400099"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        grocery_resp = await ac.get("/api/v1/stores/?service=grocery")
        pharmacy_resp = await ac.get("/api/v1/stores/?service=pharmacy")

    assert grocery_resp.status_code == 200, grocery_resp.text
    grocery_bodies = grocery_resp.json()
    assert [s["name"] for s in grocery_bodies] == ["Grocery Store"]

    assert pharmacy_resp.status_code == 200, pharmacy_resp.text
    pharmacy_bodies = pharmacy_resp.json()
    assert [s["name"] for s in pharmacy_bodies] == ["Pharma Mart"]


@pytest.mark.asyncio
async def test_list_stores_filter_unknown_service() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/stores/?service=does-not-exist")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "unknown_service"


@pytest.mark.asyncio
async def test_list_stores_filter_inactive_service(session: AsyncSession) -> None:
    # Mark the seeded grocery service inactive and verify a slug filter rejects it.
    row = await session.exec(select(Service).where(Service.slug == "grocery"))
    grocery = row.first()
    assert grocery is not None
    grocery.is_active = False
    session.add(grocery)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/stores/?service=grocery")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "unknown_service"


@pytest.mark.asyncio
async def test_list_stores_filter_includes_stockless_offering(session: AsyncSession) -> None:
    # Seller offers grocery (junction row present) but has zero StoreInventory.
    # The list endpoint must still return the store because the filter is
    # offer-based, not stock-based.
    seller_a_profile_row = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == mock_seller.id)
    )
    seller_a = seller_a_profile_row.first()
    assert seller_a is not None and seller_a.id is not None
    store_id = await _create_store_for_profile(
        session, seller_profile_id=seller_a.id, name="Empty Shelf Mart"
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/stores/?service=grocery")
    assert resp.status_code == 200, resp.text
    bodies = resp.json()
    assert any(s["id"] == store_id for s in bodies)


@pytest.mark.asyncio
async def test_list_stores_filter_with_distance_sort(session: AsyncSession) -> None:
    # Two grocery sellers at different lat/lng. Filtering by service + sort=distance
    # must respect both: only grocery sellers returned, ordered by proximity.
    seller_a_profile_row = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == mock_seller.id)
    )
    seller_a = seller_a_profile_row.first()
    assert seller_a is not None and seller_a.id is not None
    near_id = await _create_store_for_profile(
        session,
        seller_profile_id=seller_a.id,
        name="Near Grocery",
        address_overrides={"latitude": 28.4595, "longitude": 77.0266},
    )

    seller_b_id = await _seed_second_seller_with_services(
        session, email="far-grocery@kb.com", service_slugs=["grocery"]
    )
    far_id = await _create_store_for_profile(
        session,
        seller_profile_id=seller_b_id,
        name="Far Grocery",
        address_overrides={
            "latitude": 28.6000,
            "longitude": 77.2500,
            "pincode": "110001",
        },
    )

    # User sits at the "near" coordinates; near store should come first.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/stores/?service=grocery&lat=28.4595&lng=77.0266"
            "&sort=distance&radius_km=100"
        )
    assert resp.status_code == 200, resp.text
    ids = [s["id"] for s in resp.json()]
    assert ids[0] == near_id
    assert far_id in ids
```

- [ ] **Step 2: Run the new tests; confirm they fail**

Run from `backend/app/`:

```bash
uv run pytest tests/test_stores.py -k "filter" -v
```

Expected: all five tests fail. `test_list_stores_filter_by_service` and `test_list_stores_filter_with_distance_sort` will likely fail with both grocery and pharmacy stores returned (filter not implemented yet). `test_list_stores_filter_unknown_service` and `test_list_stores_filter_inactive_service` will fail with 200 instead of 400. `test_list_stores_filter_includes_stockless_offering` likely passes incidentally — that is OK, it's a non-regression lock-in.

- [ ] **Step 3: Implement the filter in `list_stores`**

Open `backend/app/src/app/api/stores.py` and replace the `list_stores` function (currently lines 108-176) with the version below. The changes vs. current:

- Add the `service` query parameter.
- Resolve slug → id with an `is_active` check; 400 on miss.
- In the no-location branch, chain a junction-membership `.where(...)` onto the statement.
- In the lat/lng branch, append `AND EXISTS (...)` to the raw SQL and bind `:service_id`.

```python
@router.get("/", response_model=List[StoreRead])
async def list_stores(
    skip: int = 0,
    limit: int = 100,
    lat: Optional[float] = Query(default=None, ge=-90.0, le=90.0),
    lng: Optional[float] = Query(default=None, ge=-180.0, le=180.0),
    radius_km: Optional[float] = Query(default=None, gt=0, le=100),
    sort: Optional[str] = Query(default=None, pattern="^distance$"),
    service: Optional[str] = Query(default=None, max_length=64),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(get_request_locale),
) -> List[StoreRead]:
    service_id: Optional[int] = None
    if service is not None:
        svc_row = await session.exec(
            select(Service.id).where(
                Service.slug == service,
                Service.is_active == True,  # noqa: E712
            )
        )
        service_id = svc_row.first()
        if service_id is None:
            raise HTTPException(status_code=400, detail="unknown_service")

    if lat is None or lng is None:
        stmt = (
            _store_with_relations_stmt()
            .where(Store.is_active)
        )
        if service_id is not None:
            from app.models.profile import SellerProfileService  # local import keeps top of file clean
            stmt = stmt.where(
                Store.seller_profile_id.in_(  # type: ignore[union-attr]
                    select(SellerProfileService.seller_profile_id).where(
                        SellerProfileService.service_id == service_id
                    )
                )
            )
        stmt = stmt.offset(skip).limit(limit)
        result = await session.exec(stmt)
        return [
            await _store_read(session, store, lang, distance_km=None)
            for store in result.all()
        ]

    point = "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography"
    if radius_km is not None:
        radius_clause = (
            f"ST_DWithin(a.geo, {point}, "
            "LEAST(s.delivery_radius_km, :user_cap) * 1000)"
        )
    else:
        radius_clause = (
            f"ST_DWithin(a.geo, {point}, s.delivery_radius_km * 1000)"
        )
    order_clause = (
        f"ST_Distance(a.geo, {point}) ASC" if sort == "distance" else "s.id ASC"
    )
    service_clause = (
        " AND EXISTS (SELECT 1 FROM sellerprofile_service sps "
        "WHERE sps.seller_profile_id = s.seller_profile_id "
        "AND sps.service_id = :service_id)"
        if service_id is not None
        else ""
    )
    sql = text(
        f"SELECT s.id, ST_Distance(a.geo, {point}) / 1000.0 AS distance_km "
        "FROM store s JOIN address a ON a.id = s.address_id "
        f"WHERE s.is_active AND a.geo IS NOT NULL AND {radius_clause}"
        f"{service_clause} "
        f"ORDER BY {order_clause} "
        "OFFSET :skip LIMIT :limit"
    )
    bind_params: dict[str, Any] = {
        "lat": lat, "lng": lng, "skip": skip, "limit": limit,
    }
    if radius_km is not None:
        bind_params["user_cap"] = radius_km
    if service_id is not None:
        bind_params["service_id"] = service_id
    rows = (
        await session.exec(sql.bindparams(**bind_params))  # type: ignore[call-overload]
    ).all()
    distance_by_id: dict[int, float] = {int(r[0]): float(r[1]) for r in rows}
    if not distance_by_id:
        return []
    stmt = (
        _store_with_relations_stmt().where(
            Store.id.in_(list(distance_by_id.keys()))  # type: ignore[union-attr]
        )
    )
    stores_unsorted = (await session.exec(stmt)).all()
    by_id = {s.id: s for s in stores_unsorted}
    ordered = [by_id[i] for i in distance_by_id.keys() if i in by_id]
    return [
        await _store_read(
            session, store, lang, distance_km=distance_by_id[store.id]
        )
        for store in ordered
    ]
```

Move the `from app.models.profile import SellerProfileService` import to the top of `stores.py` next to the other model imports (cleaner than a local import). The local-import inside the function above is shown only to make the diff readable — in the committed code it should live at the top of the file.

- [ ] **Step 4: Re-run the new tests; confirm they pass**

```bash
uv run pytest tests/test_stores.py -k "filter" -v
```

Expected: all five tests pass.

- [ ] **Step 5: Run the full stores test file to confirm no regression**

```bash
uv run pytest tests/test_stores.py -v
```

Expected: every test passes, including the pre-existing ones (`test_seller_can_create_store`, `test_get_store_localizes_service_names`, etc.).

- [ ] **Step 6: Lint and type-check**

```bash
uv run ruff check app/api/stores.py
uv run mypy app/api/stores.py
```

Expected: no errors. If mypy complains about `Store.seller_profile_id.in_(...)`, the existing `# type: ignore[union-attr]` pattern in nearby code is the canonical workaround.

- [ ] **Step 7: Commit**

```bash
git add backend/app/src/app/api/stores.py backend/app/tests/test_stores.py
git commit -m "feat(stores): add service slug filter to GET /stores/"
```

---

## Task 2: Home — wire "Shop by service" tiles to the filtered list

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/page.tsx:103-108`

### Steps

- [ ] **Step 1: Replace the tile `href`**

Open `frontend/src/app/(customer)/[locale]/page.tsx`. Find the loop that renders service tiles (currently lines 103-108):

```tsx
{services.map((s) => (
  <Link key={s.id} href="/stores" className={styles.catTile}>
    <span className={styles.catTileGlyph} aria-hidden>{serviceGlyph(s.slug)}</span>
    <span className={styles.catTileLabel}>{s.name}</span>
  </Link>
))}
```

Replace with:

```tsx
{services.map((s) => (
  <Link
    key={s.id}
    href={`/stores?service=${encodeURIComponent(s.slug)}`}
    className={styles.catTile}
  >
    <span className={styles.catTileGlyph} aria-hidden>{serviceGlyph(s.slug)}</span>
    <span className={styles.catTileLabel}>{s.name}</span>
  </Link>
))}
```

`encodeURIComponent` is defensive — service slugs are kebab-case ASCII today, but the encoder costs nothing.

- [ ] **Step 2: Smoke-test in the browser**

Start the dev stack if not already running:

```bash
./scripts/dev.sh start
```

Visit `http://localhost:3000/`. Click any "Shop by service" tile and confirm the URL becomes `/stores?service=<slug>`. The page beyond will render unfiltered until Task 3 is done — that is expected.

- [ ] **Step 3: Lint**

```bash
cd frontend && npm run lint
```

Expected: no new warnings or errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\(customer\)/\[locale\]/page.tsx
git commit -m "feat(home): link Shop by service tiles to filtered store list"
```

---

## Task 3: Stores list page — apply slug filter, header chip, Suspense wrap, deep-link store cards

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/stores/page.tsx` (whole file restructured)
- Modify: `frontend/src/app/(customer)/[locale]/stores/page.module.css` (append three classes)

### Background

`useSearchParams` in a client component opts the route out of fully static rendering. The Next.js 16 App Router fix is to wrap the consumer in a `<Suspense>` boundary. The simplest pattern: keep the default export as a small wrapper that renders `<Suspense fallback={…}>`, and move the existing logic into an inner client component (still in the same file).

The header should show a chip when a service slug is present. The slug → localized name lookup uses `/api/v1/catalog/services` (already locale-aware via the `Accept-Language` header attached by `lib/api.ts`).

### Steps

- [ ] **Step 1: Add chip styles**

Open `frontend/src/app/(customer)/[locale]/stores/page.module.css` and append:

```css
.filteredChip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  margin-top: 12px;
  border-radius: 999px;
  background: var(--color-surface-2, #f1f5f9);
  color: var(--color-text-primary, #0f172a);
  font-size: 14px;
  font-weight: 500;
}

.filteredChipLabel {
  white-space: nowrap;
}

.filteredChipClear {
  color: var(--color-accent, #2563eb);
  text-decoration: none;
  font-weight: 600;
}

.filteredChipClear:hover {
  text-decoration: underline;
}
```

If the `--color-*` custom properties used above are not defined in `frontend/src/styles/design-tokens.css`, the fallback values keep the chip readable. Do not invent new tokens — keep the additions self-contained.

- [ ] **Step 2: Restructure `page.tsx`**

Replace the entire contents of `frontend/src/app/(customer)/[locale]/stores/page.tsx` with:

```tsx
"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { prefetchStorefront } from "@/lib/storefrontCache";
import { Service, Store } from "@/types";
import styles from "./page.module.css";

export default function StoresPage() {
  const t = useTranslations("Stores");
  return (
    <Suspense
      fallback={
        <div className={styles.page}>
          <div className={styles.pageInner}>
            <div className={styles.header}>
              <h1 className={styles.title}>{t("loading")}</h1>
            </div>
          </div>
        </div>
      }
    >
      <StoresPageInner />
    </Suspense>
  );
}

function StoresPageInner() {
  const t = useTranslations("Stores");
  const locale = useLocale();
  const searchParams = useSearchParams();
  const serviceSlug = searchParams.get("service");

  const [stores, setStores] = useState<Store[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [fetching, setFetching] = useState(true);
  const { location } = useDeliveryLocation();

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- show spinner while refetching after location/slug change
    setFetching(true);
    const params = new URLSearchParams();
    if (location) {
      params.set("lat", String(location.lat));
      params.set("lng", String(location.lng));
      params.set("sort", "distance");
    }
    if (serviceSlug) {
      params.set("service", serviceSlug);
    }
    const qs = params.toString();
    const url = `/api/v1/stores/${qs ? `?${qs}` : ""}`;
    get<Store[]>(url)
      .then(setStores)
      .catch(() => setStores([]))
      .finally(() => setFetching(false));
  }, [location, serviceSlug]);

  useEffect(() => {
    if (!serviceSlug) return;
    get<Service[]>("/api/v1/catalog/services")
      .then(setServices)
      .catch(() => setServices([]));
  }, [serviceSlug]);

  const activeService = useMemo(
    () => services.find((s) => s.slug === serviceSlug) ?? null,
    [services, serviceSlug],
  );
  const activeServiceName = activeService?.name ?? serviceSlug ?? "";

  if (fetching) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <div className={styles.header}>
            <h1 className={styles.title}>{t("loading")}</h1>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        <div className={styles.header}>
          <h1 className={styles.title}>{t("browse")} {t("stores")}</h1>
          <p className={styles.subtitle}>{t("subtitle")}</p>
          {serviceSlug && (
            <div className={styles.filteredChip}>
              <span className={styles.filteredChipLabel}>
                {t("filteredHeader", { service: activeServiceName })}
              </span>
              <Link href="/stores" className={styles.filteredChipClear}>
                {t("clearFilter")}
              </Link>
            </div>
          )}
        </div>

        {stores.length === 0 && (
          <p
            className={styles.subtitle}
            style={{ textAlign: "center", padding: "32px 0" }}
          >
            {serviceSlug
              ? location
                ? t("emptyWithLocation", { service: activeServiceName })
                : t("emptyNoLocation", { service: activeServiceName })
              : location
                ? "No stores deliver to your selected location yet."
                : "No stores available."}
          </p>
        )}

        <div className={styles.grid}>
          {stores.map((store) => {
            const matchedService = serviceSlug
              ? store.services.find((s) => s.slug === serviceSlug)
              : null;
            const href = matchedService
              ? `/stores/${store.id}?service=${matchedService.id}`
              : `/stores/${store.id}`;
            return (
              <Link
                key={store.id}
                href={href}
                className={styles.card}
                id={`store-card-${store.id}`}
                onMouseEnter={() => prefetchStorefront(store.id, locale)}
                onFocus={() => prefetchStorefront(store.id, locale)}
                onTouchStart={() => prefetchStorefront(store.id, locale)}
              >
                <div className={styles.cardTop}>
                  <span className={styles.cardIcon}>
                    {store.name.charAt(0).toUpperCase()}
                  </span>
                  <span className={styles.cardStatus}>{t("openDot")}</span>
                </div>
                <div className={styles.cardBody}>
                  <h2 className={styles.cardName}>{store.name}</h2>
                  <p className={styles.cardAddress}>{formatAddress(store.address)}</p>
                  <div className={styles.cardMeta}>
                    {typeof store.distance_km === "number" && (
                      <span className={styles.cardDistance}>
                        {store.distance_km.toFixed(1)} km away
                      </span>
                    )}
                  </div>
                  <span className={styles.viewBtn}>{t("viewStore")} →</span>
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
```

Notes:

- The translation keys used here (`filteredHeader`, `clearFilter`, `emptyNoLocation`, `emptyWithLocation`) are added in Task 4 — they will throw a runtime `MISSING_MESSAGE` error from next-intl until Task 4 lands. Run Task 4 immediately after this one.
- The English fallback strings for the "no slug" branch are kept inline (matching the existing file's behavior) so we don't translate copy that wasn't translated before.
- `serviceSlug` is taken at face value — the backend validates the slug. If the user types a junk slug in the URL, the fetch fails (400) and the catch sets `stores` to `[]`; the empty-state copy still renders the (possibly nonsense) slug name. Acceptable.

- [ ] **Step 3: Lint**

```bash
cd frontend && npm run lint
```

Expected: no new errors.

- [ ] **Step 4: Build to catch type errors**

```bash
cd frontend && npm run build
```

Expected: the build succeeds. (If Task 4 has not landed yet, the build will succeed because translation keys are looked up at runtime, not build time.)

- [ ] **Step 5: Commit (no smoke test yet — translations are still missing)**

```bash
git add frontend/src/app/\(customer\)/\[locale\]/stores/page.tsx \
        frontend/src/app/\(customer\)/\[locale\]/stores/page.module.css
git commit -m "feat(stores): filter list by service slug, add header chip + Suspense"
```

---

## Task 4: Translations — add keys to all locale files

**Files:**
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/hi.json`
- Modify: `frontend/messages/mr.json`
- Modify: `frontend/messages/gu.json`
- Modify: `frontend/messages/pa.json`

### Steps

- [ ] **Step 1: Add to `frontend/messages/en.json`**

Find the `"Stores"` block and replace it with:

```json
  "Stores": {
    "loading": "Loading…",
    "browse": "Browse",
    "stores": "Stores",
    "subtitle": "Select a store to see what's available near you",
    "openDot": "● Open",
    "viewStore": "View Store →",
    "filteredHeader": "Showing {service} stores",
    "clearFilter": "Clear",
    "emptyNoLocation": "No stores offer {service} yet. Try setting a delivery location.",
    "emptyWithLocation": "No stores deliver {service} to your selected location yet."
  },
```

Inside the `"StoreDetail"` block, add `noProductsForService` next to `noProductsYet`:

```json
    "noProductsYet": "This store has no products yet.",
    "noProductsForService": "No {service} products yet at this store.",
```

- [ ] **Step 2: Add to `frontend/messages/hi.json` (Hindi)**

Mirror the same five new keys under `Stores` and the one new key under `StoreDetail`:

```json
    "filteredHeader": "{service} स्टोर दिखाए जा रहे हैं",
    "clearFilter": "साफ़ करें",
    "emptyNoLocation": "अभी {service} की कोई दुकान उपलब्ध नहीं है। डिलीवरी स्थान सेट करके देखें।",
    "emptyWithLocation": "आपके चुने हुए स्थान पर {service} की डिलीवरी अभी कोई दुकान नहीं कर रही।"
```

```json
    "noProductsForService": "इस दुकान में अभी {service} के कोई उत्पाद नहीं हैं।"
```

- [ ] **Step 3: Add to `frontend/messages/mr.json` (Marathi)**

```json
    "filteredHeader": "{service} दुकाने दाखवली जात आहेत",
    "clearFilter": "साफ करा",
    "emptyNoLocation": "सध्या {service} ची कोणतीही दुकान उपलब्ध नाही. वितरण स्थान सेट करून पाहा.",
    "emptyWithLocation": "तुमच्या निवडलेल्या ठिकाणी {service} ची डिलिव्हरी कोणतीही दुकान करत नाही."
```

```json
    "noProductsForService": "या दुकानात अद्याप {service} ची कोणतीही उत्पादने नाहीत."
```

- [ ] **Step 4: Add to `frontend/messages/gu.json` (Gujarati)**

```json
    "filteredHeader": "{service} સ્ટોર બતાવી રહ્યા છીએ",
    "clearFilter": "સાફ કરો",
    "emptyNoLocation": "હાલમાં {service} ની કોઈ દુકાન ઉપલબ્ધ નથી. ડિલિવરી સ્થાન સેટ કરીને જુઓ.",
    "emptyWithLocation": "તમારા પસંદ કરેલા સ્થાને {service} ની ડિલિવરી હાલમાં કોઈ દુકાન કરતી નથી."
```

```json
    "noProductsForService": "આ દુકાનમાં હાલમાં {service} ની કોઈ વસ્તુઓ નથી."
```

- [ ] **Step 5: Add to `frontend/messages/pa.json` (Punjabi)**

```json
    "filteredHeader": "{service} ਸਟੋਰ ਦਿਖਾਏ ਜਾ ਰਹੇ ਹਨ",
    "clearFilter": "ਸਾਫ਼ ਕਰੋ",
    "emptyNoLocation": "ਅਜੇ {service} ਦੀ ਕੋਈ ਦੁਕਾਨ ਉਪਲਬਧ ਨਹੀਂ ਹੈ। ਡਿਲੀਵਰੀ ਥਾਂ ਸੈੱਟ ਕਰਕੇ ਵੇਖੋ।",
    "emptyWithLocation": "ਤੁਹਾਡੀ ਚੁਣੀ ਹੋਈ ਥਾਂ ਉੱਤੇ {service} ਦੀ ਡਿਲੀਵਰੀ ਅਜੇ ਕੋਈ ਦੁਕਾਨ ਨਹੀਂ ਕਰ ਰਹੀ।"
```

```json
    "noProductsForService": "ਇਸ ਦੁਕਾਨ ਵਿੱਚ ਅਜੇ {service} ਦੇ ਕੋਈ ਉਤਪਾਦ ਨਹੀਂ ਹਨ।"
```

- [ ] **Step 6: Verify each file is valid JSON**

```bash
cd frontend
for f in messages/en.json messages/hi.json messages/mr.json messages/gu.json messages/pa.json; do
  node -e "JSON.parse(require('fs').readFileSync('$f','utf8')); console.log('$f OK');"
done
```

Expected: five `OK` lines, no parse errors.

- [ ] **Step 7: Smoke-test the filtered list**

Restart Next.js if needed (HMR usually picks up message-file changes):

```bash
./scripts/dev.sh restart frontend
```

Visit `http://localhost:3000/`, click the "Grocery" tile, confirm:

1. URL is `/stores?service=grocery`.
2. Header chip reads "Showing Grocery stores · Clear".
3. Only stores whose seller offers Grocery appear.
4. Clicking a store card lands on `/stores/<id>?service=<id>` (visible in the address bar before Task 5 strips it).
5. Switch locale (e.g. via the locale picker if present, or hand-edit the URL `/hi/stores?service=grocery`) and confirm the chip + empty state text localizes.

- [ ] **Step 8: Commit**

```bash
git add frontend/messages/en.json frontend/messages/hi.json \
        frontend/messages/mr.json frontend/messages/gu.json \
        frontend/messages/pa.json
git commit -m "i18n(stores): add filter chip + per-service empty state copy"
```

---

## Task 5: Store detail page — service deep-link seeding + per-service empty state

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx`

### Background

The page already keeps `activeServiceId` and `activeCategoryId` as `useState`. We want a single first-mount effect that:

1. Reads `?service=<int>` from `useSearchParams`.
2. Waits for `storefront !== null` (so we know what services have stock).
3. Picks the matched service id either from `storefront.services` (preferred, has stock) or `store.services` (fallback, offer-only). If neither, do nothing — existing `services[0]` fallback applies.
4. Sets `activeServiceId` and, when the matched service has categories, `activeCategoryId = categories[0].id`. When the requested service is in `store.services` but not in `storefront.services`, set a new `requestedMissingServiceId` state so the render can show the per-service empty branch.
5. Calls `router.replace(\`/stores/<id>\`, { scroll: false })` to drop the query param.

The effect is guarded by a `useRef` to run at most once per mount. Component remount on store-id change resets the ref naturally.

Render gating:

```
if (services.length === 0 && requestedMissingServiceId === null) -> existing "noProductsYet"
else if (requestedMissingServiceId !== null && !activeServiceNode)  -> new "noProductsForService"
else                                                                -> existing tabs + categories
```

Note that `activeServiceNode = services.find((s) => s.id === activeServiceId) ?? services[0] ?? null` — when the requested id is in `store.services` but not `storefront.services`, `services.find(...)` returns `undefined`, and we want the branch to render *without* falling back to `services[0]`. Therefore: when `requestedMissingServiceId !== null`, compute `activeServiceNode` differently — leave it `null` rather than falling back. The cleanest way is a separate memo that respects the missing-service state.

### Steps

- [ ] **Step 1: Add the imports and refs at the top of the component**

In `frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx`, update the imports at the top (currently lines 5-25) to add `useRef`, `useSearchParams`, `useRouter`:

```tsx
import { use, useState, useMemo, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
```

(Keep all other imports as-is.)

- [ ] **Step 2: Add the deep-link seed state and effect inside `StoreDetailPage`**

Inside the component body, after the existing `useState` calls and before the existing effects, add:

```tsx
const router = useRouter();
const searchParams = useSearchParams();
const seedRef = useRef(false);
const [requestedMissingServiceId, setRequestedMissingServiceId] = useState<number | null>(null);
```

Then add a new effect that fires once storefront data is available:

```tsx
useEffect(() => {
  if (seedRef.current) return;
  if (!storefront) return;
  const raw = searchParams.get("service");
  if (raw === null) {
    seedRef.current = true;
    return;
  }
  const parsed = parseInt(raw, 10);
  if (!Number.isFinite(parsed)) {
    seedRef.current = true;
    router.replace(`/stores/${storeId}`, { scroll: false });
    return;
  }
  const inStorefront = storefront.services.find((s) => s.id === parsed) ?? null;
  const inStore = storefront.store.services.find((s) => s.id === parsed) ?? null;
  if (inStorefront) {
    setActiveServiceId(inStorefront.id);
    setActiveCategoryId(inStorefront.categories[0]?.id ?? null);
  } else if (inStore) {
    setRequestedMissingServiceId(parsed);
  }
  seedRef.current = true;
  router.replace(`/stores/${storeId}`, { scroll: false });
}, [storefront, searchParams, router, storeId]);
```

- [ ] **Step 3: Adjust `activeServiceNode` to respect the missing-service branch**

Replace the existing `activeServiceNode` memo (around line 146):

```tsx
const activeServiceNode = useMemo(
  () => services.find((s) => s.id === activeServiceId) ?? services[0] ?? null,
  [services, activeServiceId],
);
```

with:

```tsx
const activeServiceNode = useMemo(() => {
  if (requestedMissingServiceId !== null) return null;
  return services.find((s) => s.id === activeServiceId) ?? services[0] ?? null;
}, [services, activeServiceId, requestedMissingServiceId]);
```

- [ ] **Step 4: Add the new empty-state render branch**

In the existing render block, find the empty-state region that currently reads:

```tsx
{services.length === 0 ? (
  <div className={styles.empty}>
    <div className={styles.emptyIcon} aria-hidden="true">🛒</div>
    <p className={styles.emptyText}>{t("noProductsYet")}</p>
  </div>
) : (
  <>
    {services.length > 1 && (
      ...
    )}
    ...
  </>
)}
```

Replace it with:

```tsx
{requestedMissingServiceId !== null ? (
  <div className={styles.empty}>
    <div className={styles.emptyIcon} aria-hidden="true">🛒</div>
    <p className={styles.emptyText}>
      {t("noProductsForService", {
        service:
          store.services.find((s) => s.id === requestedMissingServiceId)?.name ??
          "",
      })}
    </p>
  </div>
) : services.length === 0 ? (
  <div className={styles.empty}>
    <div className={styles.emptyIcon} aria-hidden="true">🛒</div>
    <p className={styles.emptyText}>{t("noProductsYet")}</p>
  </div>
) : (
  <>
    {services.length > 1 && (
      <nav className={styles.serviceTabs} aria-label={t("navAriaLabel")}>
        {services.map((svc) => (
          <button
            key={svc.id}
            type="button"
            className={`${styles.servicePill} ${
              svc.id === (activeServiceNode?.id ?? null)
                ? styles.servicePillActive
                : ""
            }`}
            onClick={() => {
              setActiveServiceId(svc.id);
              setActiveCategoryId(svc.categories[0]?.id ?? null);
            }}
            aria-current={
              svc.id === (activeServiceNode?.id ?? null) ? "true" : undefined
            }
          >
            {svc.name}
            <span className={styles.servicePillCount}>
              {serviceItemCount(svc)}
            </span>
          </button>
        ))}
      </nav>
    )}

    {activeServiceNode && (
      <div>
        {activeServiceNode.categories.map((cat) => (
          <CategorySection
            key={cat.id}
            store={store}
            service={activeServiceNode}
            category={cat}
            activeSubcategoryId={subcategoryFilters[cat.id] ?? null}
            onSubcategoryChange={handleSubcategoryChange}
          />
        ))}
      </div>
    )}
  </>
)}
```

The new branch sits in front of the existing two, so the ordering is:

1. Per-service empty (when a deep link asked for a stockless offered service).
2. Whole-store empty (no inventory at all).
3. Normal tabs + categories.

- [ ] **Step 5: Build to catch type errors**

```bash
cd frontend && npm run build
```

Expected: build succeeds. If the build complains that `storefront.store.services` is not assignable (depending on whether `StoreSummary` exposes services in your types), use `store.services` instead — `store` in scope is the typed `Store` (see line 144: `const store = storefront?.store ?? null;`). Note: the seeding effect runs only when `storefront !== null`, so `storefront.store.services` is valid there.

- [ ] **Step 6: Lint**

```bash
cd frontend && npm run lint
```

Expected: no new warnings.

- [ ] **Step 7: Smoke-test all four navigation paths**

Restart Next.js if it didn't HMR cleanly:

```bash
./scripts/dev.sh restart frontend
```

Then verify each path in the browser:

1. **Home tile → list → store (service has stock).** Click Grocery on home → land on `/stores?service=grocery` → click a grocery store with inventory. URL changes briefly to `/stores/<id>?service=<id>` then `router.replace` removes the param. The Grocery tab is selected; sidebar shows Grocery categories.
2. **Direct deep link.** Open `/stores/<id>?service=<id>` manually for a service with stock. Same outcome as above.
3. **Deep link to stockless offering.** Pick a seller that offers a service but has no inventory for it (you can verify by checking that the storefront response excludes that service). Navigate with `?service=<id>`. The page should render the "No <Service> products yet at this store." empty state, not silently switch tabs.
4. **Invalid `?service=`.** Try `?service=abc` (non-numeric). Page falls back to the first service tab as today, and the param is stripped.
5. **Back button.** From `/stores/<id>` (param stripped), press back. Browser returns to `/stores?service=grocery` (filtered list intact).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/\(customer\)/\[locale\]/stores/\[id\]/page.tsx
git commit -m "feat(stores): seed service tab from ?service= deep link"
```

---

## Task 6: Final integration check

**Files:** none modified.

### Steps

- [ ] **Step 1: Run the full backend test suite**

```bash
cd backend/app && uv run pytest -v
```

Expected: green. The new filter is exercised by the five tests in Task 1; the rest must continue to pass.

- [ ] **Step 2: Run lint + types on the backend**

```bash
cd backend/app && uv run ruff check . && uv run mypy .
```

Expected: clean.

- [ ] **Step 3: Build the frontend**

```bash
cd frontend && npm run build
```

Expected: clean build.

- [ ] **Step 4: End-to-end manual walk**

Run `./scripts/dev.sh start`, log in as a customer, set a delivery location near a seeded grocery store, and walk all five smoke-test paths from Task 5 Step 7 once more. Confirm cart behavior on the deep-linked service tab is unchanged (add a product, check that the cart binds to the right `(store, service)` sub-basket).

- [ ] **Step 5: Push and open a PR (only when the user explicitly asks)**

Per CLAUDE.md: "Wait for explicit user approval before opening PRs." Do not run `gh pr create` until the user gives the go-ahead.
