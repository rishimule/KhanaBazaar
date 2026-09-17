# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Two-phase bulk catalog import: plan against the live catalog, then apply.

Phase 1 — :func:`plan_and_stage` parses the CSV (`services/catalog_csv.py`),
resolves every slug path against the live catalog, and writes one
`catalog_import_row` per data line **without touching the catalog**. The job
row carries per-level `{create, update, noop}` counts so the preview can state
exactly what Apply would do.

Phase 2 — :func:`apply_job` walks the staged rows in chunks, upserting
service → category → subcategory → product. It is idempotent and resumable:
every processed row is stamped with `applied_at`, so re-applying a job that
died mid-run picks up where it stopped.

Design decisions worth knowing before changing anything here:

**Slug paths are identity.** A rename is "same slug, new name". The corollary
is that import cannot *move* a product between subcategories — a changed
subcategory slug is a different path, so it reads as a new product. Moves stay
in the per-row admin UI, which has the parent picker and a collision check.

**Import never deactivates.** Bulk deactivation is a separate, explicitly
confirmed action in the admin table (`POST /catalog/admin/bulk/status`). A
truncated or half-filtered CSV therefore cannot take the catalog offline.

**Soft-deleted rows are reactivated, not forked.** The partial unique indexes
cover active rows only, so a second row with the same slug would be *legal* but
confusing — and `Service.slug` is globally unique, so an inactive service would
otherwise permanently block re-importing its own slug.

**Cover images defer to the image collection.** `PUT /products/{id}` refuses to
write `image_url` because `MasterProductImage` owns the cover. Import honours
that: on create it sets `image_url` and seeds image row 0 (mirroring
`create_product_admin`); on update it only does so when the product has no
images at all, so a curated collection is never clobbered.

**Diffs compare formatted prices.** `_format_price` is used on both sides of the
base-price comparison so that a freshly exported, unedited file always plans as
all-noop regardless of float representation.

**Query shape differs by phase, deliberately.** Planning is batched — four
bulk `IN (...)` lookups for the whole file — because it runs inside the upload
request (450 rows measured at ~160ms). Apply resolves one product per row and
upserts translations with a SELECT each, so a fully translated row costs ~6
queries; that is fine on a worker (450 rows applied in under 4s) and it keeps
the per-row savepoint isolation simple. Do not "optimize" apply into a batched
pre-fetch without checking whether it still lets one bad row fail alone.

**Search sync is left to the standard `after_commit` hook.** An earlier draft
suppressed the per-row hook and enqueued `reindex_products_by_subcategory` once
per touched subcategory instead. That is a pessimization: those "batch" tasks
are fan-out dispatchers (`search/tasks.py`), so each one re-indexes every
product in the subcategory — touching 3 products in a 500-product subcategory
would enqueue 500 tasks where the hook enqueues 3. The hook dedupes by product
id per commit, so a chunk enqueues at most `APPLY_CHUNK` tasks and the total is
proportional to what actually changed. Parent renames are already routed to the
category/subcategory fan-out by the same hook.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import (
    Category,
    CategoryTranslation,
    LanguageCode,
    MasterProduct,
    MasterProductImage,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.catalog_import import (
    CatalogImportJob,
    CatalogImportRow,
    CatalogImportRowAction,
    CatalogImportStatus,
)
from app.services.catalog_csv import (
    ALL_COLUMNS,
    TRANSLATABLE_LANGS,
    CatalogCsvError,
    ParsedRow,
    parse_catalog_csv,
)

logger = logging.getLogger(__name__)

_EN = LanguageCode.English.value
_LEVELS = ("service", "category", "subcategory", "product")

# Rows per transaction during apply. Small enough that a worker death loses
# little, large enough that per-chunk parent resolution amortizes.
APPLY_CHUNK = 200

# Statuses a caller may START an apply from. `Failed` is included so a partially
# applied job can be resumed — already-applied rows are skipped by `applied_at`.
APPLIABLE_STATUSES = (CatalogImportStatus.Validated, CatalogImportStatus.Failed)

# What `apply_job` itself will accept. `Applying` is included because the HTTP
# endpoint claims the job (flips it to Applying and commits) BEFORE enqueueing,
# so that a click gives immediate feedback and a second click is rejected by the
# status guard rather than enqueueing a duplicate task.
#
# A hard-killed worker (SIGKILL, so the except branch never runs) therefore
# leaves a job stuck in Applying that the endpoint will refuse. That is
# deliberate — the recovery is to upload the same file again rather than to
# race a second worker onto the same rows. A fresh job re-plans against the
# current catalog, so whatever already landed comes back as `noop` and only the
# remainder is create/update. The import page says so when a job sits in
# Applying.
_WORKER_ACCEPTED_STATUSES = (*APPLIABLE_STATUSES, CatalogImportStatus.Applying)

ServiceKey = str
CategoryKey = Tuple[str, str]
SubcategoryKey = Tuple[str, str, str]
ProductKey = Tuple[str, str, str, str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format_price(value: float) -> str:
    """Currency-style rendering used by BOTH export and diffing.

    Comparing formatted strings rather than floats is what guarantees an
    unedited export re-imports as a noop.
    """
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def _empty_counts() -> Dict[str, Dict[str, int]]:
    return {level: {"create": 0, "update": 0, "noop": 0} for level in _LEVELS}


# ─── Desired-state extraction ──────────────────────────────────


def _desired_parent(level: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Provided (non-blank) fields for one parent level, keys unprefixed."""
    out: Dict[str, Any] = {}
    for suffix, key in (("name", "name"), ("description", "description"), ("sort_order", "sort_order")):
        column = f"{level}_{suffix}"
        if column in data:
            out[key] = data[column]
    return out


def _desired_product(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if "product_name" in data:
        out["name"] = data["product_name"]
    if "product_description" in data:
        out["description"] = data["product_description"]
    if "base_price" in data:
        out["base_price"] = data["base_price"]
    for key in ("brand", "unit"):
        if key in data:
            out[key] = data[key]
    if "product_image_url" in data:
        out["image_url"] = data["product_image_url"]
    translations: Dict[str, Dict[str, str]] = {}
    for lang in TRANSLATABLE_LANGS:
        name = data.get(f"product_name_{lang}")
        if not name:
            continue
        entry = {"name": name}
        desc = data.get(f"product_desc_{lang}")
        if desc:
            entry["description"] = desc
        translations[lang] = entry
    if translations:
        out["translations"] = translations
    return out


def _path(row_data: Dict[str, Any], depth: int) -> Optional[Tuple[str, ...]]:
    """Slug tuple for the first ``depth`` levels, or None if any slug is absent."""
    parts: List[str] = []
    for level in _LEVELS[:depth]:
        slug = row_data.get(f"{level}_slug")
        if not isinstance(slug, str):
            return None
        parts.append(slug)
    return tuple(parts)


# ─── Existing-row lookup (prefer active, else newest inactive) ──


def _pick(rows: Sequence[Any]) -> Any:
    """Active row wins; otherwise the newest soft-deleted one."""
    active = [r for r in rows if r.is_active]
    if active:
        return max(active, key=lambda r: r.id or 0)
    return max(rows, key=lambda r: r.id or 0) if rows else None


async def _load_services(
    session: AsyncSession, slugs: Iterable[str]
) -> Dict[ServiceKey, Service]:
    wanted = sorted(set(slugs))
    if not wanted:
        return {}
    rows = (
        await session.exec(select(Service).where(col(Service.slug).in_(wanted)))
    ).all()
    grouped: Dict[str, List[Service]] = defaultdict(list)
    for row in rows:
        grouped[row.slug].append(row)
    return {slug: _pick(items) for slug, items in grouped.items()}


async def _load_children(
    session: AsyncSession,
    model: Any,
    parent_attr: str,
    pairs: Set[Tuple[int, str]],
) -> Dict[Tuple[int, str], Any]:
    """Load ``model`` rows for a set of ``(parent_id, slug)`` pairs.

    One query with an IN on each side, then an exact-pair filter in Python —
    cheaper than a query per pair and bounded by the file's parent fan-out.
    """
    if not pairs:
        return {}
    parent_ids = {p for p, _ in pairs}
    slugs = {s for _, s in pairs}
    rows = (
        await session.exec(
            select(model)
            .where(col(getattr(model, parent_attr)).in_(sorted(parent_ids)))
            .where(col(model.slug).in_(sorted(slugs)))
        )
    ).all()
    grouped: Dict[Tuple[int, str], List[Any]] = defaultdict(list)
    for row in rows:
        key = (getattr(row, parent_attr), row.slug)
        if key in pairs:
            grouped[key].append(row)
    return {key: _pick(items) for key, items in grouped.items()}


async def _load_en_names(
    session: AsyncSession, model: Any, fk: str, ids: Iterable[Optional[int]]
) -> Dict[int, Any]:
    wanted = sorted({i for i in ids if i is not None})
    if not wanted:
        return {}
    rows = (
        await session.exec(
            select(model)
            .where(col(getattr(model, fk)).in_(wanted))
            .where(model.language_code == _EN)
        )
    ).all()
    return {getattr(r, fk): r for r in rows}


async def _load_product_translations(
    session: AsyncSession, product_ids: Iterable[Optional[int]]
) -> Dict[int, Dict[str, MasterProductTranslation]]:
    wanted = sorted({i for i in product_ids if i is not None})
    if not wanted:
        return {}
    rows = (
        await session.exec(
            select(MasterProductTranslation).where(
                col(MasterProductTranslation.master_product_id).in_(wanted)
            )
        )
    ).all()
    grouped: Dict[int, Dict[str, MasterProductTranslation]] = defaultdict(dict)
    for row in rows:
        grouped[row.master_product_id][row.language_code] = row
    return grouped


async def _load_products_with_images(
    session: AsyncSession, product_ids: Iterable[Optional[int]]
) -> Set[int]:
    wanted = sorted({i for i in product_ids if i is not None})
    if not wanted:
        return set()
    rows = (
        await session.exec(
            select(MasterProductImage.master_product_id).where(
                col(MasterProductImage.master_product_id).in_(wanted)
            )
        )
    ).all()
    return set(rows)


# ─── Diffing ───────────────────────────────────────────────────


def _parent_needs_update(entity: Any, en: Any, desired: Dict[str, Any]) -> bool:
    if not entity.is_active:
        return True
    if "name" in desired and (en.name if en else None) != desired["name"]:
        return True
    if "description" in desired:
        current = (getattr(en, "description", None) or "") if en else ""
        if current != desired["description"]:
            return True
    if "sort_order" in desired and entity.sort_order != desired["sort_order"]:
        return True
    return False


def _product_needs_update(
    product: MasterProduct,
    translations: Dict[str, MasterProductTranslation],
    has_images: bool,
    desired: Dict[str, Any],
) -> bool:
    if not product.is_active:
        return True
    en = translations.get(_EN)
    if "name" in desired and (en.name if en else None) != desired["name"]:
        return True
    if "description" in desired:
        current = (en.description if en else "") or ""
        if current != desired["description"]:
            return True
    if "base_price" in desired and _format_price(product.base_price) != _format_price(
        desired["base_price"]
    ):
        return True
    for key in ("brand", "unit"):
        if key in desired and (getattr(product, key) or "") != desired[key]:
            return True
    # Only a product with no images at all takes its cover from the CSV.
    if "image_url" in desired and not has_images:
        if (product.image_url or "") != desired["image_url"]:
            return True
    for lang, entry in desired.get("translations", {}).items():
        existing = translations.get(lang)
        if existing is None or existing.name != entry["name"]:
            return True
        if "description" in entry and (existing.description or "") != entry["description"]:
            return True
    return False


# ─── Phase 1: plan + stage ─────────────────────────────────────


async def plan_and_stage(
    session: AsyncSession,
    *,
    filename: str,
    raw: bytes,
    admin_id: int,
) -> CatalogImportJob:
    """Parse + validate + resolve the file, staging one row per data line.

    Writes nothing to the catalog. Raises :class:`CatalogCsvError` for
    file-level problems; row-level problems are staged on the rows. Caller
    commits.
    """
    parsed = parse_catalog_csv(raw)  # may raise CatalogCsvError

    good = [r for r in parsed if r.ok]

    # Resolve the hierarchy top-down. A level whose parent is being created is
    # itself definitionally a create, so each step only looks up paths whose
    # parent already exists in the live catalog.
    service_state = await _resolve_services(session, good)
    category_state = await _resolve_categories(session, good, service_state)
    subcategory_state = await _resolve_subcategories(session, good, category_state)
    product_state = await _resolve_products(session, good, subcategory_state)

    # Counts are per DISTINCT path, not per row: every row under one new
    # category reports `category: create`, but the category is created once.
    counts = _empty_counts()
    for level, state in (
        ("service", service_state),
        ("category", category_state),
        ("subcategory", subcategory_state),
        ("product", product_state),
    ):
        for verdict, _entity in state.values():
            counts[level][verdict] += 1

    error_rows = len(parsed) - len(good)
    job = CatalogImportJob(
        filename=filename[:255],
        status=CatalogImportStatus.Validated,
        created_by_admin_id=admin_id,
        total_rows=len(parsed),
        error_rows=error_rows,
        plan=counts,
        applied={},
    )
    session.add(job)
    await session.flush()
    assert job.id is not None

    staged: List[CatalogImportRow] = []
    for row in parsed:
        if not row.ok:
            staged.append(
                CatalogImportRow(
                    job_id=job.id,
                    line_number=row.line_number,
                    action=CatalogImportRowAction.Error,
                    data=row.data,
                    errors=row.errors,
                    level_plan={},
                )
            )
            continue
        level_plan = {
            "service": service_state[_require_path(row, 1)][0],
            "category": category_state[_require_path(row, 2)][0],
            "subcategory": subcategory_state[_require_path(row, 3)][0],
            "product": product_state[_require_path(row, 4)][0],
        }
        staged.append(
            CatalogImportRow(
                job_id=job.id,
                line_number=row.line_number,
                action=_row_action(level_plan),
                data=row.data,
                errors=[],
                level_plan=level_plan,
            )
        )
    session.add_all(staged)
    await session.flush()
    return job


def _require_path(row: ParsedRow, depth: int) -> Tuple[str, ...]:
    path = _path(row.data, depth)
    assert path is not None, "validated rows always carry all four slugs"
    return path


def _row_action(level_plan: Dict[str, str]) -> CatalogImportRowAction:
    """A row's headline verdict: create > update > noop across its four levels."""
    verdicts = set(level_plan.values())
    if "create" in verdicts:
        return CatalogImportRowAction.Create
    if "update" in verdicts:
        return CatalogImportRowAction.Update
    return CatalogImportRowAction.Noop


async def _resolve_services(
    session: AsyncSession, rows: Sequence[ParsedRow]
) -> Dict[Tuple[str, ...], Tuple[str, Optional[Service]]]:
    desired_by_path: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for row in rows:
        path = _require_path(row, 1)
        merged = desired_by_path.setdefault(path, {})
        merged.update(_desired_parent("service", row.data))

    existing = await _load_services(session, (p[0] for p in desired_by_path))
    en = await _load_en_names(
        session,
        ServiceTranslation,
        "service_id",
        (s.id for s in existing.values() if s.id is not None),
    )

    out: Dict[Tuple[str, ...], Tuple[str, Optional[Service]]] = {}
    for path, desired in desired_by_path.items():
        entity = existing.get(path[0])
        if entity is None:
            out[path] = ("create", None)
        else:
            verdict = (
                "update"
                if _parent_needs_update(entity, en.get(entity.id or -1), desired)
                else "noop"
            )
            out[path] = (verdict, entity)
    return out


async def _resolve_categories(
    session: AsyncSession,
    rows: Sequence[ParsedRow],
    service_state: Dict[Tuple[str, ...], Tuple[str, Optional[Service]]],
) -> Dict[Tuple[str, ...], Tuple[str, Optional[Category]]]:
    desired_by_path: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for row in rows:
        path = _require_path(row, 2)
        merged = desired_by_path.setdefault(path, {})
        merged.update(_desired_parent("category", row.data))

    pairs: Set[Tuple[int, str]] = set()
    for path in desired_by_path:
        _verdict, service = service_state[path[:1]]
        if service is not None and service.id is not None:
            pairs.add((service.id, path[1]))
    existing = await _load_children(session, Category, "service_id", pairs)
    en = await _load_en_names(
        session,
        CategoryTranslation,
        "category_id",
        (c.id for c in existing.values() if c.id is not None),
    )

    out: Dict[Tuple[str, ...], Tuple[str, Optional[Category]]] = {}
    for path, desired in desired_by_path.items():
        _verdict, service = service_state[path[:1]]
        entity = (
            existing.get((service.id, path[1]))
            if service is not None and service.id is not None
            else None
        )
        if entity is None:
            out[path] = ("create", None)
        else:
            verdict = (
                "update"
                if _parent_needs_update(entity, en.get(entity.id or -1), desired)
                else "noop"
            )
            out[path] = (verdict, entity)
    return out


async def _resolve_subcategories(
    session: AsyncSession,
    rows: Sequence[ParsedRow],
    category_state: Dict[Tuple[str, ...], Tuple[str, Optional[Category]]],
) -> Dict[Tuple[str, ...], Tuple[str, Optional[Subcategory]]]:
    desired_by_path: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for row in rows:
        path = _require_path(row, 3)
        merged = desired_by_path.setdefault(path, {})
        merged.update(_desired_parent("subcategory", row.data))

    pairs: Set[Tuple[int, str]] = set()
    for path in desired_by_path:
        _verdict, category = category_state[path[:2]]
        if category is not None and category.id is not None:
            pairs.add((category.id, path[2]))
    existing = await _load_children(session, Subcategory, "category_id", pairs)
    en = await _load_en_names(
        session,
        SubcategoryTranslation,
        "subcategory_id",
        (s.id for s in existing.values() if s.id is not None),
    )

    out: Dict[Tuple[str, ...], Tuple[str, Optional[Subcategory]]] = {}
    for path, desired in desired_by_path.items():
        _verdict, category = category_state[path[:2]]
        entity = (
            existing.get((category.id, path[2]))
            if category is not None and category.id is not None
            else None
        )
        if entity is None:
            out[path] = ("create", None)
        else:
            verdict = (
                "update"
                if _parent_needs_update(entity, en.get(entity.id or -1), desired)
                else "noop"
            )
            out[path] = (verdict, entity)
    return out


async def _resolve_products(
    session: AsyncSession,
    rows: Sequence[ParsedRow],
    subcategory_state: Dict[Tuple[str, ...], Tuple[str, Optional[Subcategory]]],
) -> Dict[Tuple[str, ...], Tuple[str, Optional[MasterProduct]]]:
    desired_by_path: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for row in rows:
        path = _require_path(row, 4)
        desired_by_path[path] = _desired_product(row.data)

    pairs: Set[Tuple[int, str]] = set()
    for path in desired_by_path:
        _verdict, sub = subcategory_state[path[:3]]
        if sub is not None and sub.id is not None:
            pairs.add((sub.id, path[3]))
    existing = await _load_children(session, MasterProduct, "subcategory_id", pairs)
    ids = [p.id for p in existing.values() if p.id is not None]
    translations = await _load_product_translations(session, ids)
    with_images = await _load_products_with_images(session, ids)

    out: Dict[Tuple[str, ...], Tuple[str, Optional[MasterProduct]]] = {}
    for path, desired in desired_by_path.items():
        _verdict, sub = subcategory_state[path[:3]]
        entity = (
            existing.get((sub.id, path[3]))
            if sub is not None and sub.id is not None
            else None
        )
        if entity is None:
            out[path] = ("create", None)
        else:
            verdict = (
                "update"
                if _product_needs_update(
                    entity,
                    translations.get(entity.id or -1, {}),
                    (entity.id in with_images),
                    desired,
                )
                else "noop"
            )
            out[path] = (verdict, entity)
    return out


# ─── Phase 2: apply ────────────────────────────────────────────


class _Applier:
    """Per-run state for an apply pass.

    Caches resolved parents across chunks so a 3,000-row file sharing 20
    categories does not re-resolve them 3,000 times, and accumulates the
    subcategory/category ids that need a Meilisearch refresh.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.counts = _empty_counts()
        self.services: Dict[ServiceKey, Service] = {}
        self.categories: Dict[CategoryKey, Category] = {}
        self.subcategories: Dict[SubcategoryKey, Subcategory] = {}
        self.failed_rows = 0

    # ─── parent upserts ───

    async def _upsert_translation(
        self,
        model: Any,
        fk: str,
        entity_id: int,
        lang: str,
        name: Optional[str],
        description: Optional[str],
        *,
        description_required: bool,
    ) -> bool:
        """Insert or patch one translation row. Returns True if anything changed."""
        existing = (
            await self.session.exec(
                select(model)
                .where(col(getattr(model, fk)) == entity_id)
                .where(model.language_code == lang)
            )
        ).first()
        if existing is None:
            if name is None:
                return False
            kwargs: Dict[str, Any] = {fk: entity_id, "language_code": lang, "name": name}
            if description is not None:
                kwargs["description"] = description
            elif description_required:
                kwargs["description"] = ""
            self.session.add(model(**kwargs))
            return True
        changed = False
        if name is not None and existing.name != name:
            existing.name = name
            changed = True
        if description is not None and (existing.description or "") != description:
            existing.description = description
            changed = True
        if changed:
            self.session.add(existing)
        return changed

    async def _resolve_service(self, slug: str, desired: Dict[str, Any]) -> Service:
        cached = self.services.get(slug)
        if cached is not None:
            return cached
        found = (await _load_services(self.session, [slug])).get(slug)
        if found is None:
            entity = Service(
                slug=slug,
                is_active=True,
                sort_order=int(desired.get("sort_order", 0)),
            )
            self.session.add(entity)
            await self.session.flush()
            assert entity.id is not None
            await self._upsert_translation(
                ServiceTranslation,
                "service_id",
                entity.id,
                _EN,
                desired.get("name") or slug,
                desired.get("description"),
                description_required=False,
            )
            self.counts["service"]["create"] += 1
        else:
            entity = found
            assert entity.id is not None
            changed = False
            if not entity.is_active:
                entity.is_active = True
                changed = True
            if "sort_order" in desired and entity.sort_order != desired["sort_order"]:
                entity.sort_order = int(desired["sort_order"])
                changed = True
            if changed:
                self.session.add(entity)
            trans_changed = await self._upsert_translation(
                ServiceTranslation,
                "service_id",
                entity.id,
                _EN,
                desired.get("name"),
                desired.get("description"),
                description_required=False,
            )
            self.counts["service"]["update" if (changed or trans_changed) else "noop"] += 1
        await self.session.flush()
        self.services[slug] = entity
        return entity

    async def _resolve_category(
        self, key: CategoryKey, service: Service, desired: Dict[str, Any]
    ) -> Category:
        cached = self.categories.get(key)
        if cached is not None:
            return cached
        assert service.id is not None
        found = (
            await _load_children(
                self.session, Category, "service_id", {(service.id, key[1])}
            )
        ).get((service.id, key[1]))
        if found is None:
            entity = Category(
                service_id=service.id,
                slug=key[1],
                is_active=True,
                sort_order=int(desired.get("sort_order", 0)),
            )
            self.session.add(entity)
            await self.session.flush()
            assert entity.id is not None
            await self._upsert_translation(
                CategoryTranslation,
                "category_id",
                entity.id,
                _EN,
                desired.get("name") or key[1],
                desired.get("description"),
                description_required=False,
            )
            self.counts["category"]["create"] += 1
        else:
            entity = found
            assert entity.id is not None
            changed = False
            if not entity.is_active:
                entity.is_active = True
                changed = True
            if "sort_order" in desired and entity.sort_order != desired["sort_order"]:
                entity.sort_order = int(desired["sort_order"])
                changed = True
            if changed:
                self.session.add(entity)
            trans_changed = await self._upsert_translation(
                CategoryTranslation,
                "category_id",
                entity.id,
                _EN,
                desired.get("name"),
                desired.get("description"),
                description_required=False,
            )
            self.counts["category"]["update" if (changed or trans_changed) else "noop"] += 1
        await self.session.flush()
        self.categories[key] = entity
        return entity

    async def _resolve_subcategory(
        self, key: SubcategoryKey, category: Category, desired: Dict[str, Any]
    ) -> Subcategory:
        cached = self.subcategories.get(key)
        if cached is not None:
            return cached
        assert category.id is not None
        found = (
            await _load_children(
                self.session, Subcategory, "category_id", {(category.id, key[2])}
            )
        ).get((category.id, key[2]))
        if found is None:
            entity = Subcategory(
                category_id=category.id,
                slug=key[2],
                is_active=True,
                sort_order=int(desired.get("sort_order", 0)),
            )
            self.session.add(entity)
            await self.session.flush()
            assert entity.id is not None
            await self._upsert_translation(
                SubcategoryTranslation,
                "subcategory_id",
                entity.id,
                _EN,
                desired.get("name") or key[2],
                desired.get("description"),
                description_required=False,
            )
            self.counts["subcategory"]["create"] += 1
        else:
            entity = found
            assert entity.id is not None
            changed = False
            if not entity.is_active:
                entity.is_active = True
                changed = True
            if "sort_order" in desired and entity.sort_order != desired["sort_order"]:
                entity.sort_order = int(desired["sort_order"])
                changed = True
            if changed:
                self.session.add(entity)
            trans_changed = await self._upsert_translation(
                SubcategoryTranslation,
                "subcategory_id",
                entity.id,
                _EN,
                desired.get("name"),
                desired.get("description"),
                description_required=False,
            )
            self.counts["subcategory"][
                "update" if (changed or trans_changed) else "noop"
            ] += 1
        await self.session.flush()
        self.subcategories[key] = entity
        return entity

    async def resolve_parents(self, rows: Sequence[CatalogImportRow]) -> None:
        """Create/update every parent referenced by ``rows``.

        Runs outside the per-row savepoints on purpose: many rows depend on the
        same parent, so a parent failure must fail the chunk rather than leave
        a rolled-back parent in the cache.
        """
        for row in rows:
            data = row.data
            svc_path = _path(data, 1)
            cat_path = _path(data, 2)
            sub_path = _path(data, 3)
            assert svc_path and cat_path and sub_path
            service = await self._resolve_service(
                svc_path[0], _desired_parent("service", data)
            )
            category = await self._resolve_category(
                (cat_path[0], cat_path[1]), service, _desired_parent("category", data)
            )
            await self._resolve_subcategory(
                (sub_path[0], sub_path[1], sub_path[2]),
                category,
                _desired_parent("subcategory", data),
            )

    # ─── product upsert ───

    async def apply_product(self, row: CatalogImportRow) -> None:
        data = row.data
        sub_path = _path(data, 3)
        assert sub_path is not None
        subcategory = self.subcategories[(sub_path[0], sub_path[1], sub_path[2])]
        assert subcategory.id is not None
        slug = data["product_slug"]
        desired = _desired_product(data)

        found = (
            await _load_children(
                self.session, MasterProduct, "subcategory_id", {(subcategory.id, slug)}
            )
        ).get((subcategory.id, slug))

        if found is None:
            product = MasterProduct(
                subcategory_id=subcategory.id,
                slug=slug,
                image_url=desired.get("image_url"),
                base_price=float(desired["base_price"]),
                brand=desired.get("brand"),
                unit=desired.get("unit"),
                is_active=True,
            )
            self.session.add(product)
            await self.session.flush()
            assert product.id is not None
            await self._upsert_translation(
                MasterProductTranslation,
                "master_product_id",
                product.id,
                _EN,
                desired.get("name") or slug,
                desired.get("description", ""),
                description_required=True,
            )
            # Mirror create_product_admin: seed image row 0 so the collection
            # (the source of truth for the cover) and image_url agree from the
            # start, otherwise the first image added later silently replaces it.
            if desired.get("image_url"):
                self.session.add(
                    MasterProductImage(
                        master_product_id=product.id,
                        position=0,
                        url=desired["image_url"],
                        source="external",
                        storage_key=None,
                    )
                )
            self.counts["product"]["create"] += 1
        else:
            product = found
            assert product.id is not None
            changed = False
            if not product.is_active:
                product.is_active = True
                changed = True
            if "base_price" in desired and _format_price(
                product.base_price
            ) != _format_price(desired["base_price"]):
                product.base_price = float(desired["base_price"])
                changed = True
            for key in ("brand", "unit"):
                if key in desired and (getattr(product, key) or "") != desired[key]:
                    setattr(product, key, desired[key])
                    changed = True
            if desired.get("image_url"):
                has_images = bool(
                    await _load_products_with_images(self.session, [product.id])
                )
                if not has_images and (product.image_url or "") != desired["image_url"]:
                    product.image_url = desired["image_url"]
                    self.session.add(
                        MasterProductImage(
                            master_product_id=product.id,
                            position=0,
                            url=desired["image_url"],
                            source="external",
                            storage_key=None,
                        )
                    )
                    changed = True
            if changed:
                self.session.add(product)
            trans_changed = await self._upsert_translation(
                MasterProductTranslation,
                "master_product_id",
                product.id,
                _EN,
                desired.get("name"),
                desired.get("description"),
                description_required=True,
            )
            self.counts["product"]["update" if (changed or trans_changed) else "noop"] += 1

        for lang, entry in desired.get("translations", {}).items():
            await self._upsert_translation(
                MasterProductTranslation,
                "master_product_id",
                product.id,
                lang,
                entry["name"],
                entry.get("description"),
                description_required=True,
            )

        await self.session.flush()


async def apply_job(session: AsyncSession, job_id: int) -> CatalogImportJob:
    """Write the staged rows of ``job_id`` into the catalog.

    Commits as it goes (one transaction per :data:`APPLY_CHUNK` rows) and stamps
    ``applied_at`` on every processed row, so a crash leaves an honest partial
    state that a second Apply resumes. Meilisearch sync rides on the standard
    `after_commit` hook — see the module docstring for why this does not try to
    batch it.
    """
    job = await session.get(CatalogImportJob, job_id)
    if job is None:
        raise ValueError(f"catalog import job {job_id} not found")
    if job.status not in _WORKER_ACCEPTED_STATUSES:
        raise ValueError(f"job {job_id} is {job.status.value}, not appliable")

    # Usually already Applying (the endpoint claimed it); this covers a direct
    # service-level call.
    job.status = CatalogImportStatus.Applying
    job.failure_reason = None
    session.add(job)
    await session.commit()

    applier = _Applier(session)
    try:
        while True:
            rows = (
                await session.exec(
                    select(CatalogImportRow)
                    .where(CatalogImportRow.job_id == job_id)
                    .where(col(CatalogImportRow.action) != CatalogImportRowAction.Error)
                    .where(col(CatalogImportRow.applied_at).is_(None))
                    .order_by(col(CatalogImportRow.line_number))
                    .limit(APPLY_CHUNK)
                )
            ).all()
            if not rows:
                break

            await applier.resolve_parents(rows)
            for row in rows:
                # Savepoint per row: an unexpected per-row failure (a slug that
                # raced into existence since validation, say) is recorded and
                # skipped instead of poisoning the whole chunk's transaction.
                try:
                    async with session.begin_nested():
                        await applier.apply_product(row)
                except Exception as exc:  # noqa: BLE001 - recorded per row
                    applier.failed_rows += 1
                    row.apply_error = str(exc)[:500]
                    logger.warning(
                        "catalog_import.row_failed job=%s line=%s err=%s",
                        job_id,
                        row.line_number,
                        exc,
                    )
                # Always stamped, successes and failures alike — the chunk query
                # selects on `applied_at IS NULL` and would otherwise loop.
                row.applied_at = _now()
                session.add(row)
            await session.commit()

        job.applied = applier.counts
        job.applied_at = _now()
        if applier.failed_rows:
            job.status = CatalogImportStatus.Failed
            job.failure_reason = (
                f"{applier.failed_rows} row(s) failed to apply; see the row report"
            )
        else:
            job.status = CatalogImportStatus.Applied
        session.add(job)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        job = await session.get(CatalogImportJob, job_id)
        if job is not None:
            job.status = CatalogImportStatus.Failed
            job.failure_reason = str(exc)[:500]
            job.applied = applier.counts
            session.add(job)
            await session.commit()
        raise

    return job


# ─── Export ────────────────────────────────────────────────────


async def export_catalog_rows(
    session: AsyncSession,
    *,
    service_id: Optional[int] = None,
    category_id: Optional[int] = None,
    subcategory_id: Optional[int] = None,
    include_inactive: bool = False,
) -> List[Dict[str, Any]]:
    """Every product as an import-shaped dict, newest ancestry first.

    Column-for-column round-trippable: feeding the result straight back into
    :func:`plan_and_stage` must plan as all-noop.
    """
    stmt = (
        select(MasterProduct, Subcategory, Category, Service)
        .join(Subcategory, col(MasterProduct.subcategory_id) == col(Subcategory.id))
        .join(Category, col(Subcategory.category_id) == col(Category.id))
        .join(Service, col(Category.service_id) == col(Service.id))
    )
    if not include_inactive:
        stmt = (
            stmt.where(col(MasterProduct.is_active).is_(True))
            .where(col(Subcategory.is_active).is_(True))
            .where(col(Category.is_active).is_(True))
            .where(col(Service.is_active).is_(True))
        )
    if subcategory_id is not None:
        stmt = stmt.where(col(Subcategory.id) == subcategory_id)
    if category_id is not None:
        stmt = stmt.where(col(Category.id) == category_id)
    if service_id is not None:
        stmt = stmt.where(col(Service.id) == service_id)
    stmt = stmt.order_by(
        col(Service.sort_order),
        col(Service.slug),
        col(Category.sort_order),
        col(Category.slug),
        col(Subcategory.sort_order),
        col(Subcategory.slug),
        col(MasterProduct.slug),
    )

    joined = (await session.exec(stmt)).all()
    if not joined:
        return []

    svc_en = await _load_en_names(
        session, ServiceTranslation, "service_id", (s.id for _p, _sub, _c, s in joined)
    )
    cat_en = await _load_en_names(
        session, CategoryTranslation, "category_id", (c.id for _p, _sub, c, _s in joined)
    )
    sub_en = await _load_en_names(
        session,
        SubcategoryTranslation,
        "subcategory_id",
        (sub.id for _p, sub, _c, _s in joined),
    )
    prod_trans = await _load_product_translations(
        session, (p.id for p, _sub, _c, _s in joined)
    )

    out: List[Dict[str, Any]] = []
    for product, subcategory, category, service in joined:
        s_t = svc_en.get(service.id or -1)
        c_t = cat_en.get(category.id or -1)
        sub_t = sub_en.get(subcategory.id or -1)
        translations = prod_trans.get(product.id or -1, {})
        en = translations.get(_EN)
        record: Dict[str, Any] = {
            "service_slug": service.slug,
            "service_name": s_t.name if s_t else service.slug,
            "service_description": (getattr(s_t, "description", None) or ""),
            "service_sort_order": service.sort_order,
            "category_slug": category.slug,
            "category_name": c_t.name if c_t else category.slug,
            "category_description": (getattr(c_t, "description", None) or ""),
            "category_sort_order": category.sort_order,
            "subcategory_slug": subcategory.slug,
            "subcategory_name": sub_t.name if sub_t else subcategory.slug,
            "subcategory_description": (getattr(sub_t, "description", None) or ""),
            "subcategory_sort_order": subcategory.sort_order,
            "product_slug": product.slug,
            "product_name": en.name if en else product.slug,
            "product_description": (en.description if en else "") or "",
            "base_price": _format_price(product.base_price),
            "brand": product.brand or "",
            "unit": product.unit or "",
            "product_image_url": product.image_url or "",
        }
        for lang in TRANSLATABLE_LANGS:
            row = translations.get(lang)
            record[f"product_name_{lang}"] = row.name if row else ""
            record[f"product_desc_{lang}"] = (row.description if row else "") or ""
        out.append(record)
    return out


def rows_to_csv(records: Sequence[Dict[str, Any]]) -> str:
    """Serialize export records using the canonical column order."""
    import csv
    import io

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(ALL_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for record in records:
        writer.writerow(record)
    return buf.getvalue()


__all__ = [
    "APPLIABLE_STATUSES",
    "APPLY_CHUNK",
    "CatalogCsvError",
    "apply_job",
    "export_catalog_rows",
    "plan_and_stage",
    "rows_to_csv",
]
