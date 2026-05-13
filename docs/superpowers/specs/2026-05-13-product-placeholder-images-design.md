# Product Placeholder Images — Design

**Date:** 2026-05-13
**Status:** Approved (brainstorm)

## Problem

Every product in the dev seed (1500 rows) carries an `image_url` like `/images/products/<slug>.jpg`, but `frontend/public/images/` does not exist. All product cards render the fail-fallback. We want each product to have a real placeholder image without committing hundreds of binary files to the repo.

## Goal

Every seeded product resolves to one of 2–3 themed placeholder images, grouped at **category** level. Pure URL substitution in seed data — no frontend code changes, no local image assets.

## Non-goals

- Sub-category-level theming (rejected: ~300 subs × 3 = ~900 URLs is too much manual curation).
- Per-product unique imagery (rejected: not the point of placeholders).
- Runtime image generation, image proxy, CDN of our own.
- Mutating production data (seed only).

## Approach

1. **Single source of truth: `CATEGORY_IMAGE_POOLS`** in `backend/app/src/app/db/_dev_seed_data.py`.
   - Type: `dict[str, list[str]]`
   - Key: category slug (covers both anchor categories — `grocery`, `electronics`, `pharmacy` — and all `EXTRA_CATEGORIES`, ~100 total).
   - Value: list of 3 hand-picked Unsplash direct image URLs (`https://images.unsplash.com/photo-<id>?w=400&auto=format&fit=crop`). Direct URLs are stable, free, require no API key, and respect Unsplash's licensing for free use.
2. **Helper** `_image_for(category_slug: str, index: int) -> str` in `_dev_seed_data.py`:
   - `pool = CATEGORY_IMAGE_POOLS[category_slug]`
   - `assert pool, f"empty pool for {category_slug}"`
   - returns `pool[index % len(pool)]`
   - raises `KeyError` if category slug missing — fail loud during seed so we catch coverage gaps.
3. **Extra product generation** (`_generate_extra_products` in `_dev_seed_data.py`):
   - Replace `f"/images/products/{unique_slug}.jpg"` with `_image_for(cat["slug"], i)` where `i` is the per-subcategory loop index (0..4).
4. **Anchor products** (135 hand-written entries in `dev_seed.py` `PRODUCTS` list):
   - Remove the inline `"image_url": "/images/products/<slug>.jpg"` field from every entry.
   - **At module load time** (right after `PRODUCTS` is constructed, before `seed_demo_data` consumes it), run a post-process loop that:
     - builds `SUBCAT_TO_CATEGORY = {sub["slug"]: sub["category_slug"] for sub in SUBCATEGORIES}` once,
     - walks `PRODUCTS` in order, keeping a `defaultdict(int)` counter keyed by `subcategory_slug` for index-within-subcategory,
     - sets `product["image_url"] = _image_for(SUBCAT_TO_CATEGORY[product["subcategory_slug"]], counter[sub_slug])` then increments the counter.
5. **Coverage assertion (test):** extend `tests/test_dev_seed.py` with a check that every seeded `MasterProduct` has a non-null, non-empty `image_url`, and that every category slug in `SUBCATEGORIES` + anchor subcategory list has an entry in `CATEGORY_IMAGE_POOLS`.

## Round-robin example

Category `grocery` has pool `[A, B, C]`. Subcategory `everyday-vegetables` has 5 products in order. Assignments: `A, B, C, A, B`.

## Why category-level

~100 categories × 3 URLs = 300 hand-picked URLs. Subcategory-level would be ~900 — too much curation. Coarser theming is acceptable because customers don't compare images across products in the same subcategory expecting variation.

## Why direct Unsplash URLs, not local files

- Zero repo bloat (~900 product photos would be 50+ MB).
- No licensing folder, no attribution file to maintain (Unsplash license permits free use without attribution; we'll note it in a comment near `CATEGORY_IMAGE_POOLS`).
- The Unsplash `source.unsplash.com/?query=` keyword endpoint was retired in 2024; direct `images.unsplash.com/photo-<id>` URLs are the supported pattern.
- ProductCard already shows graceful fallback on image load failure (`imgFailed` state in `frontend/src/components/ProductCard.tsx:87`).

## Out of scope

Test fixtures in `tests/test_store_product_detail.py`, `tests/test_storefront_endpoint.py`, and `tests/test_catalog.py` construct `MasterProduct` rows directly (bypassing seed) with hardcoded `/images/products/*.jpg` paths. These tests verify catalog/storefront logic, not image rendering; their fake URLs work for assertions regardless. Not touched by this change.

## Files touched

| File | Change |
|------|--------|
| `backend/app/src/app/db/_dev_seed_data.py` | Add `CATEGORY_IMAGE_POOLS` dict (~100 keys × 3 URLs), add `_image_for` helper, update `_generate_extra_products` to call helper. |
| `backend/app/src/app/db/dev_seed.py` | Strip `image_url` from ~135 anchor `PRODUCTS` entries, add post-process assignment loop. |
| `backend/app/tests/test_dev_seed.py` | Add coverage assertion (every product has image_url; every category has pool entry). |

No frontend changes. No migration changes. No new dependencies.

## Risks

- **External CDN dependency.** Unsplash CDN goes down → all product images blank. Acceptable for dev seed; ProductCard fallback covers it.
- **URL rot.** Unsplash photos can be removed by their author. Mitigation: pick high-engagement photos that are unlikely to be deleted; if one rots, replace it in `CATEGORY_IMAGE_POOLS` (single-place fix).
- **Category coverage gaps.** Missing pool entry → seed crashes loud. Test asserts coverage so CI catches before commit.

## Testing

- `uv run pytest tests/test_dev_seed.py -v` — coverage assertion passes.
- `uv run python -m app.db.local_reset` (or equivalent reset script) — seed runs cleanly.
- Manual browser smoke: open `/stores/<id>`, confirm product cards show real images from Unsplash CDN.

## Open questions

None.
