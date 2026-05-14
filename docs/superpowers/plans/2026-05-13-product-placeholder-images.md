# Product Placeholder Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every seeded `MasterProduct` resolves to one of 3 themed placeholder images from a free stock CDN, grouped at category level.

**Architecture:** Add `CATEGORY_IMAGE_POOLS: dict[str, list[str]]` and `_image_for(category_slug, index)` helper to `_dev_seed_data.py`. Both extra-product generation and a new anchor-product post-process loop call the helper. Pools are built by a tiny generator over LoremFlickr keyword URLs (`https://loremflickr.com/400/400/<keyword>?lock=<n>`) — Flickr-backed, themed by category slug, no manual URL curation. Spec called for Unsplash, but Unsplash's `source.unsplash.com/?query=` endpoint was retired in 2024 and direct photo IDs cannot be fabricated; LoremFlickr is the same class (free, themed, no API key) and was implicit in the user's "free stock photos" choice.

**Tech Stack:** Python 3.12, pytest, sqlmodel. No new dependencies. LoremFlickr serves images directly via URL pattern.

---

### Task 1: Add `CATEGORY_IMAGE_POOLS` and `_image_for` helper with coverage test

**Files:**
- Modify: `backend/app/src/app/db/_dev_seed_data.py` (add near top, after `_RNG` line)
- Modify: `backend/app/tests/test_dev_seed.py` (add new test)

- [ ] **Step 1: Write the failing test**

Open `backend/app/tests/test_dev_seed.py`. Add this test at the bottom of the file:

```python
def test_category_image_pools_cover_every_category() -> None:
    """Every category slug used in CATEGORIES must have a non-empty image pool."""
    from app.db._dev_seed_data import CATEGORY_IMAGE_POOLS, _image_for
    from app.db.dev_seed import CATEGORIES

    for cat in CATEGORIES:
        slug = cat["slug"]
        assert slug in CATEGORY_IMAGE_POOLS, f"missing pool for category {slug}"
        pool = CATEGORY_IMAGE_POOLS[slug]
        assert isinstance(pool, list) and len(pool) >= 2, f"pool for {slug} must have >= 2 URLs, got {pool}"
        for url in pool:
            assert url.startswith("http"), f"non-http url in pool {slug}: {url}"

    # Helper round-robins deterministically.
    sample_slug = next(iter(CATEGORY_IMAGE_POOLS))
    pool = CATEGORY_IMAGE_POOLS[sample_slug]
    assert _image_for(sample_slug, 0) == pool[0]
    assert _image_for(sample_slug, 1) == pool[1 % len(pool)]
    assert _image_for(sample_slug, len(pool)) == pool[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_dev_seed.py::test_category_image_pools_cover_every_category -v`

Expected: FAIL with `ImportError: cannot import name 'CATEGORY_IMAGE_POOLS'` (or similar).

- [ ] **Step 3: Add the constant and helper**

Open `backend/app/src/app/db/_dev_seed_data.py`. Right after the `_RNG = random.Random(42)` line (around line 26), insert:

```python
# ---------------------------------------------------------------------------
# PRODUCT IMAGE POOLS (3 themed CDN URLs per category)
# LoremFlickr is Flickr-backed; URLs are stable for fixed (keyword, lock) pairs
# and require no API key. ProductCard already shows a graceful fallback on
# image-load failure, so transient CDN blips degrade gracefully.
# ---------------------------------------------------------------------------
_CATEGORY_IMAGE_KEYWORDS: dict[str, str] = {
    # Grocery (anchor + extras)
    "fruits-vegetables": "fruits,vegetables",
    "dairy-bakery": "dairy,bakery",
    "staples-grains": "rice,flour,grains",
    "beverages": "beverage,drink",
    "snacks": "snacks,chips",
    "frozen-foods": "frozen,food",
    "breakfast-cereals": "cereal,breakfast",
    "condiments-spices": "spices,sauce",
    "sweets-desserts": "dessert,sweets",
    "ready-to-eat": "ready,meal",
    # Electronics (anchor + extras)
    "laptops-computers": "laptop,computer",
    "mobiles-tablets": "smartphone,tablet",
    "audio-accessories": "headphones,audio",
    "cameras": "camera,photography",
    "gaming": "gaming,console",
    "tv-entertainment": "television,tv",
    "computer-accessories": "keyboard,mouse",
    "smart-home": "smart,home",
    "networking": "router,network",
    "kitchen-electronics": "kitchen,appliance",
    # Pharmacy (anchor + extras)
    "medicines": "medicine,pharmacy",
    "personal-care": "skincare,personal",
    "wellness-nutrition": "vitamins,wellness",
    "baby-care": "baby,care",
    "womens-health": "womens,health",
    "mens-grooming": "men,grooming",
    "ayurveda": "ayurveda,herbs",
    "first-aid": "first,aid",
    "medical-devices": "medical,device",
    "eye-ear-care": "eye,ear",
    # Food
    "north-indian": "indian,curry",
    "south-indian": "dosa,idli",
    "chinese": "chinese,noodles",
    "italian-continental": "pasta,pizza",
    "fast-food": "burger,fries",
    "biryani-rice": "biryani,rice",
    "desserts-sweets": "dessert,cake",
    "beverages-cafe": "coffee,cafe",
    # Bakery
    "cakes-pastries": "cake,pastry",
    "breads-buns": "bread,buns",
    "cookies-biscuits": "cookies,biscuits",
    "donuts-puffs": "donut,pastry",
    "savory-bakery": "croissant,bakery",
    # Meat & Seafood
    "chicken": "chicken,meat",
    "mutton": "mutton,meat",
    "fish": "fish,seafood",
    "prawns-shrimp": "prawns,shrimp",
    "eggs": "eggs,carton",
    # Beauty
    "makeup": "makeup,cosmetics",
    "fragrances": "perfume,fragrance",
    "skincare-premium": "skincare,beauty",
    "haircare-premium": "haircare,salon",
    "nail-care": "nails,polish",
    # Stationery
    "school-stationery": "stationery,school",
    "office-supplies": "office,supplies",
    "art-craft": "art,paint",
    "books": "books,reading",
    "calculators": "calculator,office",
    # Pet
    "dog-food": "dog,food",
    "cat-food": "cat,food",
    "pet-accessories": "pet,accessory",
    "pet-grooming": "pet,grooming",
    "fish-bird-supplies": "aquarium,fish",
    # Home & Kitchen
    "cookware": "cookware,pan",
    "tableware": "plates,tableware",
    "storage-organisation": "storage,box",
    "home-decor": "decor,interior",
    "home-appliances": "appliance,kitchen",
    # Flowers & Plants
    "bouquets": "bouquet,flowers",
    "indoor-plants": "plant,indoor",
    "garden-essentials": "garden,tools",
    "seeds-bulbs": "seeds,gardening",
    "vases-pots": "pot,vase",
    # Sports & Fitness
    "gym-equipment": "gym,equipment",
    "yoga-mats": "yoga,mat",
    "sports-gear": "sports,equipment",
    "fitness-wearables": "fitness,watch",
    "athletic-wear": "athletic,clothing",
}


def _build_image_pool(keyword: str) -> list[str]:
    """3 LoremFlickr URLs sharing a keyword but with different `lock` seeds so each
    one resolves to a different stable photo."""
    return [f"https://loremflickr.com/400/400/{keyword}?lock={n}" for n in (1, 2, 3)]


CATEGORY_IMAGE_POOLS: dict[str, list[str]] = {
    slug: _build_image_pool(keyword) for slug, keyword in _CATEGORY_IMAGE_KEYWORDS.items()
}


def _image_for(category_slug: str, index: int) -> str:
    """Round-robin pick from the category's image pool. Fail loud on missing
    coverage so seed runs surface gaps immediately."""
    pool = CATEGORY_IMAGE_POOLS[category_slug]
    assert pool, f"empty image pool for category {category_slug}"
    return pool[index % len(pool)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend/app && uv run pytest tests/test_dev_seed.py::test_category_image_pools_cover_every_category -v`

Expected: PASS.

If FAIL with "missing pool for category X" — extend `_CATEGORY_IMAGE_KEYWORDS` with that slug. The 9 anchor + 91 extra category slugs are the only valid keys; the test enumerates them via `CATEGORIES` so the failure message names the missing one. Pick a 1–2 word comma-separated keyword (e.g. `"slug-x": "keyword1,keyword2"`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/db/_dev_seed_data.py backend/app/tests/test_dev_seed.py
git commit -m "feat(seed): add CATEGORY_IMAGE_POOLS and _image_for helper"
```

---

### Task 2: Wire `_image_for` into extra product generation

**Files:**
- Modify: `backend/app/src/app/db/_dev_seed_data.py:947` (the `image_url` line inside `_generate_extra_products`)
- Modify: `backend/app/tests/test_dev_seed.py` (add test)

- [ ] **Step 1: Write the failing test**

Add this test at the bottom of `backend/app/tests/test_dev_seed.py`:

```python
def test_extra_products_use_cdn_image_urls() -> None:
    """Every generated extra product must have a non-empty CDN URL drawn from its
    parent category's image pool."""
    from app.db._dev_seed_data import CATEGORY_IMAGE_POOLS, EXTRA_PRODUCTS, EXTRA_SUBCATEGORIES

    sub_to_cat = {sub["slug"]: sub["category_slug"] for sub in EXTRA_SUBCATEGORIES}
    assert EXTRA_PRODUCTS, "EXTRA_PRODUCTS should be non-empty"
    for product in EXTRA_PRODUCTS:
        url = product["image_url"]
        assert url.startswith("http"), f"extra product {product['slug']} has non-http url: {url}"
        cat_slug = sub_to_cat[product["subcategory_slug"]]
        assert url in CATEGORY_IMAGE_POOLS[cat_slug], (
            f"extra product {product['slug']} url not in pool for {cat_slug}: {url}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_dev_seed.py::test_extra_products_use_cdn_image_urls -v`

Expected: FAIL — assertion shows current `/images/products/<slug>.jpg` path does not start with `http`.

- [ ] **Step 3: Update `_generate_extra_products`**

In `backend/app/src/app/db/_dev_seed_data.py`, find the `image_url` line inside the `for i, brand in enumerate(brands):` loop (currently line 947):

```python
                "image_url": f"/images/products/{unique_slug}.jpg",
```

Replace with:

```python
                "image_url": _image_for(cat["slug"], i),
```

(The surrounding loop already has `cat = _CATEGORY_BY_SLUG[sub["category_slug"]]` and `i` is the 0..4 brand index, so no other change is needed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend/app && uv run pytest tests/test_dev_seed.py::test_extra_products_use_cdn_image_urls -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/db/_dev_seed_data.py backend/app/tests/test_dev_seed.py
git commit -m "feat(seed): wire extra products through CATEGORY_IMAGE_POOLS"
```

---

### Task 3: Strip anchor `image_url` strings and add post-process loop

**Files:**
- Modify: `backend/app/src/app/db/dev_seed.py` (strip `image_url` from PRODUCTS entries, add post-process loop after the `PRODUCTS` list)
- Modify: `backend/app/tests/test_dev_seed.py` (add test)

- [ ] **Step 1: Write the failing test**

Add this test at the bottom of `backend/app/tests/test_dev_seed.py`:

```python
def test_anchor_products_use_cdn_image_urls() -> None:
    """Every anchor product must have a non-empty CDN URL drawn from its parent
    category's image pool. Anchor products are the 135 hand-curated entries in
    PRODUCTS (everything before EXTRA_PRODUCTS gets appended)."""
    from app.db._dev_seed_data import CATEGORY_IMAGE_POOLS, EXTRA_PRODUCTS
    from app.db.dev_seed import PRODUCTS, SUBCATEGORIES

    sub_to_cat = {sub["slug"]: sub["category_slug"] for sub in SUBCATEGORIES}
    anchor_count = len(PRODUCTS) - len(EXTRA_PRODUCTS)
    assert anchor_count == 135, f"expected 135 anchor products, got {anchor_count}"
    for product in PRODUCTS[:anchor_count]:
        url = product["image_url"]
        assert url.startswith("http"), f"anchor product {product['slug']} has non-http url: {url}"
        cat_slug = sub_to_cat[product["subcategory_slug"]]
        assert url in CATEGORY_IMAGE_POOLS[cat_slug], (
            f"anchor product {product['slug']} url not in pool for {cat_slug}: {url}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_dev_seed.py::test_anchor_products_use_cdn_image_urls -v`

Expected: FAIL — anchor products still carry `/images/products/<slug>.jpg`.

- [ ] **Step 3: Strip `image_url` field from every anchor product line**

In `backend/app/src/app/db/dev_seed.py`, find the `PRODUCTS: list[dict[str, Any]] = [` block starting around line 296. Each anchor entry currently looks like:

```python
    {"subcategory_slug": "leafy-greens", "slug": "spinach-bunch-palak", "name": "Spinach Bunch (Palak)", "description": "Fresh palak bunch — iron-rich and tender", "image_url": "/images/products/spinach.jpg", "base_price": 25},
```

Remove `"image_url": "/images/products/<...>.jpg", ` from all 135 anchor entries. Run this Python one-liner from `backend/app/`:

```bash
cd backend/app
python3 - <<'PYEOF'
import re
p = "src/app/db/dev_seed.py"
text = open(p).read()
new, n = re.subn(r'"image_url":\s*"/images/products/[^"]+",\s*', "", text)
assert "/images/products/" not in new, "leftover /images/products/ strings"
open(p, "w").write(new)
print(f"stripped {n} occurrences")
PYEOF
```

Expected stdout: `stripped 135 occurrences`. If the count is anything other than 135, abort, revert with `git checkout src/app/db/dev_seed.py`, and inspect manually.

Then verify the path is gone:

```bash
grep -n "/images/products/" backend/app/src/app/db/dev_seed.py || echo "ok: no /images/products/ left"
```

Expected: `ok: no /images/products/ left`.

- [ ] **Step 4: Add post-process loop after the PRODUCTS list**

In `backend/app/src/app/db/dev_seed.py`, the `PRODUCTS` list ends right before `PRODUCTS.extend(EXTRA_PRODUCTS)` (search for that line). Just BEFORE `PRODUCTS.extend(EXTRA_PRODUCTS)`, insert this block:

```python
# Assign placeholder images from CATEGORY_IMAGE_POOLS to every anchor product.
# Round-robin by index-within-subcategory to evenly distribute the 3 URLs.
# Must run before PRODUCTS.extend(EXTRA_PRODUCTS) so we touch anchor entries
# only (extras already carry their URLs from _generate_extra_products).
from collections import defaultdict as _defaultdict

from app.db._dev_seed_data import _image_for as _seed_image_for

_SUBCAT_TO_CATEGORY: dict[str, str] = {sub["slug"]: sub["category_slug"] for sub in SUBCATEGORIES}
_anchor_sub_counter: dict[str, int] = _defaultdict(int)
for _product in PRODUCTS:
    _sub_slug = _product["subcategory_slug"]
    _cat_slug = _SUBCAT_TO_CATEGORY[_sub_slug]
    _product["image_url"] = _seed_image_for(_cat_slug, _anchor_sub_counter[_sub_slug])
    _anchor_sub_counter[_sub_slug] += 1

del _defaultdict, _seed_image_for, _SUBCAT_TO_CATEGORY, _anchor_sub_counter, _product, _sub_slug, _cat_slug
```

(Leading underscores on locals avoid polluting the module namespace; the trailing `del` cleans up.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend/app && uv run pytest tests/test_dev_seed.py::test_anchor_products_use_cdn_image_urls -v`

Expected: PASS.

- [ ] **Step 6: Run full dev_seed test suite to confirm no regressions**

Run: `cd backend/app && uv run pytest tests/test_dev_seed.py -v`

Expected: ALL PASS (including pre-existing count/login tests). If any pre-existing test fails, read its error carefully — most likely a count drift if the strip script removed a comma or character it shouldn't have. Inspect the diff (`git diff src/app/db/dev_seed.py`) and revert + re-run the sed if so.

- [ ] **Step 7: Commit**

```bash
git add backend/app/src/app/db/dev_seed.py backend/app/tests/test_dev_seed.py
git commit -m "feat(seed): assign anchor product images from CATEGORY_IMAGE_POOLS"
```

---

### Task 4: Lint, type-check, and final full-suite verification

**Files:**
- None (verification only).

- [ ] **Step 1: Ruff lint**

Run: `cd backend/app && uv run ruff check .`

Expected: clean. If complaints about unused imports inside `dev_seed.py` post-process block, address them (the `del` line should remove any leftover; if Ruff still complains, suppress with `# noqa: F841` on the offending local).

- [ ] **Step 2: Mypy type check**

Run: `cd backend/app && uv run mypy .`

Expected: clean. If mypy complains about `_seed_image_for` returning `str` and `_product["image_url"]` being `Optional[str]` (it shouldn't — assignment widens), the existing `Any` typing on PRODUCTS dicts makes this a non-issue. If a new error appears in `_dev_seed_data.py`, it's likely a missing annotation on `_CATEGORY_IMAGE_KEYWORDS` or `CATEGORY_IMAGE_POOLS` — they should already carry annotations from Task 1.

- [ ] **Step 3: Full backend test suite**

Run: `cd backend/app && uv run pytest -v`

Expected: ALL PASS. Existing fixtures in `test_store_product_detail.py`, `test_storefront_endpoint.py`, and `test_catalog.py` construct `MasterProduct` rows directly with their own hardcoded `image_url` values (out of scope per spec) — they remain green.

- [ ] **Step 4: Manual browser smoke (optional but recommended)**

Reset the local seed and check a store page:

```bash
./scripts/dev.sh start
cd backend/app && uv run python -m app.db.local_reset
```

Open `http://localhost:3000/stores/<any-id>` in a browser. Product cards should show real photos from `loremflickr.com` instead of the fallback glyph. Network tab should show 200s on `loremflickr.com/400/400/...`. (If LoremFlickr is slow on first request, that's expected — Flickr backend caches after first hit.)

- [ ] **Step 5: Push branch**

```bash
git push -u origin feat/product-placeholder-images
```

(Do NOT open a PR yet — wait for explicit user approval per project rules.)
