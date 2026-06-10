# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin-only CRUD + paginated list endpoints for catalog entities.

Every route requires `get_current_admin`. Lists return a `PagedResponse`
shaped `{items, total, page, page_size}` so the `/admin/catalog` frontend
can render pagination. Search (`q`) matches against entity slug AND the
joined translation name. `is_active` filter defaults to `None` (no
filter) — pass `true` for active-only, `false` for soft-deleted.

Public read endpoints stay in `api/catalog.py` and filter `is_active`
implicitly so customers never see soft-deleted rows.
"""

import re
from typing import List, Sequence, Type

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlmodel import or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.base import User
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
from app.schemas.catalog_admin import (
    CategoryAdminCreate,
    CategoryAdminRead,
    CategoryAdminUpdate,
    ProductAdminCreate,
    ProductAdminRead,
    ProductAdminUpdate,
    ProductImageRead,
    ProductImageReorder,
    ProductImageUrlCreate,
    ServiceAdminRead,
    ServiceCreate,
    ServiceUpdate,
    SubcategoryAdminRead,
    SubcategoryCreate,
    SubcategoryUpdate,
    TranslationOut,
    TranslationUpsert,
)
from app.schemas.pagination import PagedResponse
from app.services import product_images as product_image_svc
from app.services.catalog_translations import (
    load_category_translations,
    load_product_translations,
    load_service_translations,
    load_subcategory_translations,
)
from app.services.image_processing import ImageValidationError

router = APIRouter(prefix="/admin", tags=["catalog-admin"])

_EN = LanguageCode.English.value
_VALID_LANGS = {lc.value for lc in LanguageCode}


def _slugify(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return base or "item"


def _serialize_translations(rows: Sequence[object]) -> List[TranslationOut]:
    out: List[TranslationOut] = []
    for r in rows:
        out.append(
            TranslationOut(
                language_code=r.language_code,  # type: ignore[attr-defined]
                name=r.name,  # type: ignore[attr-defined]
                description=getattr(r, "description", None),
            )
        )
    return out


def _english(translations: Sequence[object]) -> object | None:
    for r in translations:
        if r.language_code == _EN:  # type: ignore[attr-defined]
            return r
    return None


def _english_name(translations: Sequence[object], fallback: str) -> str:
    en = _english(translations)
    return en.name if en is not None else fallback  # type: ignore[attr-defined]


def _english_description(translations: Sequence[object]) -> str | None:
    en = _english(translations)
    if en is None:
        return None
    return getattr(en, "description", None)


def _resolve_active_filter(is_active: bool | None) -> bool:
    """Child-count queries should reflect the active filter currently in
    use. Default (None / All) and Active filter both count active children;
    Inactive filter counts inactive children."""
    return is_active if is_active is not None else True


# ─── Services ──────────────────────────────────────────────────


def _service_admin_read(
    svc: Service, translations: Sequence[ServiceTranslation], child_count: int = 0
) -> ServiceAdminRead:
    assert svc.id is not None
    return ServiceAdminRead(
        id=svc.id,
        created_at=svc.created_at,
        updated_at=svc.updated_at,
        slug=svc.slug,
        name=_english_name(translations, svc.slug),
        description=_english_description(translations),
        image_url=svc.icon_url,
        is_active=svc.is_active,
        sort_order=svc.sort_order,
        child_count=child_count,
        translations=_serialize_translations(translations),
    )


@router.get("/services", response_model=PagedResponse[ServiceAdminRead])
async def list_services_admin(
    q: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> PagedResponse[ServiceAdminRead]:
    stmt = select(Service)
    if q:
        like = f"%{q.lower()}%"
        stmt = (
            stmt.outerjoin(
                ServiceTranslation,
                ServiceTranslation.service_id == Service.id,  # type: ignore[arg-type]
            )
            .where(
                or_(
                    Service.slug.ilike(like),  # type: ignore[attr-defined]
                    ServiceTranslation.name.ilike(like),  # type: ignore[attr-defined]
                )
            )
            .distinct()
        )
    if is_active is not None:
        stmt = stmt.where(Service.is_active == is_active)
    stmt = stmt.order_by(Service.sort_order, Service.id)  # type: ignore[arg-type]
    offset = (page - 1) * page_size

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await session.exec(count_stmt)).one())

    page_result = await session.exec(stmt.offset(offset).limit(page_size))
    services = list(page_result.all())
    ids = [s.id for s in services if s.id is not None]
    trans = await load_service_translations(session, ids)

    # Active-category counts per service (respect filter).
    counts: dict[int, int] = {}
    if ids:
        active_for_children = _resolve_active_filter(is_active)
        cat_count_rows = (await session.exec(
            select(Category.service_id, func.count())  # type: ignore[arg-type]
            .where(Category.service_id.in_(ids))  # type: ignore[attr-defined]
            .where(Category.is_active == active_for_children)
            .group_by(Category.service_id)  # type: ignore[arg-type]
        )).all()
        counts = {row[0]: row[1] for row in cat_count_rows}

    items = [
        _service_admin_read(svc, trans.get(svc.id, []), counts.get(svc.id, 0))
        for svc in services
        if svc.id is not None
    ]
    return PagedResponse[ServiceAdminRead](
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/services/{service_id}", response_model=ServiceAdminRead)
async def get_service_admin(
    service_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ServiceAdminRead:
    svc = await session.get(Service, service_id)
    if svc is None:
        raise HTTPException(status_code=404, detail="not_found")
    trans = (await session.exec(
        select(ServiceTranslation).where(ServiceTranslation.service_id == service_id)
    )).all()
    return _service_admin_read(svc, list(trans))


@router.post("/services", response_model=ServiceAdminRead)
async def create_service_admin(
    payload: ServiceCreate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ServiceAdminRead:
    slug = (payload.slug or _slugify(payload.name)).lower()
    existing = await session.exec(select(Service).where(Service.slug == slug))
    if existing.first() is not None:
        raise HTTPException(status_code=409, detail="slug_exists")

    svc = Service(
        slug=slug,
        icon_url=payload.image_url,
        is_active=True,
        sort_order=payload.sort_order,
    )
    session.add(svc)
    await session.flush()
    assert svc.id is not None
    en = ServiceTranslation(
        service_id=svc.id,
        language_code=_EN,
        name=payload.name,
        description=payload.description,
    )
    session.add(en)
    await session.flush()
    response = _service_admin_read(svc, [en])
    await session.commit()
    return response


@router.put("/services/{service_id}", response_model=ServiceAdminRead)
async def update_service_admin(  # noqa: C901
    service_id: int,
    payload: ServiceUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ServiceAdminRead:
    svc = await session.get(Service, service_id)
    if svc is None:
        raise HTTPException(status_code=404, detail="not_found")

    if payload.slug is not None and payload.slug != svc.slug:
        new_slug = payload.slug.lower()
        conflict = await session.exec(
            select(Service).where(
                Service.slug == new_slug,
                Service.id != svc.id,  # type: ignore[arg-type]
            )
        )
        if conflict.first() is not None:
            raise HTTPException(status_code=409, detail="slug_exists")
        svc.slug = new_slug

    if payload.image_url is not None:
        svc.icon_url = payload.image_url
    if payload.sort_order is not None:
        svc.sort_order = payload.sort_order
    if payload.is_active is not None:
        svc.is_active = payload.is_active

    if payload.name is not None or payload.description is not None:
        trans_q = await session.exec(
            select(ServiceTranslation).where(
                ServiceTranslation.service_id == svc.id,
                ServiceTranslation.language_code == _EN,
            )
        )
        en = trans_q.first()
        if en is None:
            en = ServiceTranslation(
                service_id=svc.id,
                language_code=_EN,
                name=payload.name or svc.slug,
                description=payload.description,
            )
            session.add(en)
        else:
            if payload.name is not None:
                en.name = payload.name
            if payload.description is not None:
                en.description = payload.description

    session.add(svc)
    await session.flush()
    all_trans = (await session.exec(
        select(ServiceTranslation).where(ServiceTranslation.service_id == svc.id)
    )).all()
    response = _service_admin_read(svc, list(all_trans))
    await session.commit()
    return response


@router.delete("/services/{service_id}")
async def delete_service_admin(
    service_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    svc = await session.get(Service, service_id)
    if svc is None:
        raise HTTPException(status_code=404, detail="not_found")
    svc.is_active = False
    session.add(svc)
    await session.commit()
    return {"detail": "deactivated"}


# ─── Categories ────────────────────────────────────────────────


def _category_admin_read(
    cat: Category, translations: Sequence[CategoryTranslation], child_count: int = 0
) -> CategoryAdminRead:
    assert cat.id is not None
    return CategoryAdminRead(
        id=cat.id,
        created_at=cat.created_at,
        updated_at=cat.updated_at,
        service_id=cat.service_id,
        slug=cat.slug,
        name=_english_name(translations, cat.slug),
        description=_english_description(translations),
        image_url=cat.image_url,
        is_active=cat.is_active,
        sort_order=cat.sort_order,
        child_count=child_count,
        translations=_serialize_translations(translations),
    )


@router.get("/categories", response_model=PagedResponse[CategoryAdminRead])
async def list_categories_admin(
    service_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> PagedResponse[CategoryAdminRead]:
    stmt = select(Category)
    if q:
        like = f"%{q.lower()}%"
        stmt = (
            stmt.outerjoin(
                CategoryTranslation,
                CategoryTranslation.category_id == Category.id,  # type: ignore[arg-type]
            )
            .where(
                or_(
                    Category.slug.ilike(like),  # type: ignore[attr-defined]
                    CategoryTranslation.name.ilike(like),  # type: ignore[attr-defined]
                )
            )
            .distinct()
        )
    if service_id is not None:
        stmt = stmt.where(Category.service_id == service_id)
    if is_active is not None:
        stmt = stmt.where(Category.is_active == is_active)
    stmt = stmt.order_by(Category.service_id, Category.sort_order, Category.id)  # type: ignore[arg-type]
    offset = (page - 1) * page_size

    total = int((await session.exec(select(func.count()).select_from(stmt.subquery()))).one())
    cats = list((await session.exec(stmt.offset(offset).limit(page_size))).all())
    ids = [c.id for c in cats if c.id is not None]
    trans = await load_category_translations(session, ids)

    counts: dict[int, int] = {}
    if ids:
        active_for_children = _resolve_active_filter(is_active)
        sub_count_rows = (await session.exec(
            select(Subcategory.category_id, func.count())  # type: ignore[arg-type]
            .where(Subcategory.category_id.in_(ids))  # type: ignore[attr-defined]
            .where(Subcategory.is_active == active_for_children)
            .group_by(Subcategory.category_id)  # type: ignore[arg-type]
        )).all()
        counts = {row[0]: row[1] for row in sub_count_rows}

    items = [
        _category_admin_read(c, trans.get(c.id, []), counts.get(c.id, 0))
        for c in cats
        if c.id is not None
    ]
    return PagedResponse[CategoryAdminRead](
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/categories/{category_id}", response_model=CategoryAdminRead)
async def get_category_admin(
    category_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> CategoryAdminRead:
    cat = await session.get(Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="not_found")
    trans = (await session.exec(
        select(CategoryTranslation).where(CategoryTranslation.category_id == category_id)
    )).all()
    return _category_admin_read(cat, list(trans))


@router.post("/categories", response_model=CategoryAdminRead)
async def create_category_admin(
    payload: CategoryAdminCreate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> CategoryAdminRead:
    svc = await session.get(Service, payload.service_id)
    if svc is None:
        raise HTTPException(status_code=404, detail="parent_not_found")
    slug = (payload.slug or _slugify(payload.name)).lower()
    clash = await session.exec(
        select(Category.id)
        .where(Category.service_id == payload.service_id)
        .where(Category.slug == slug)
        .where(Category.is_active.is_(True))  # type: ignore[attr-defined]
    )
    if clash.first() is not None:
        raise HTTPException(status_code=409, detail="slug_exists")
    cat = Category(
        service_id=payload.service_id,
        slug=slug,
        image_url=payload.image_url,
        is_active=True,
        sort_order=payload.sort_order,
    )
    session.add(cat)
    await session.flush()
    assert cat.id is not None
    en = CategoryTranslation(
        category_id=cat.id,
        language_code=_EN,
        name=payload.name,
        description=payload.description,
    )
    session.add(en)
    await session.flush()
    response = _category_admin_read(cat, [en], 0)
    await session.commit()
    return response


@router.put("/categories/{category_id}", response_model=CategoryAdminRead)
async def update_category_admin(  # noqa: C901
    category_id: int,
    payload: CategoryAdminUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> CategoryAdminRead:
    cat = await session.get(Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="not_found")

    target_service = cat.service_id
    if payload.service_id is not None and payload.service_id != cat.service_id:
        parent = await session.get(Service, payload.service_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="parent_not_found")
        target_service = payload.service_id

    target_slug = (payload.slug or cat.slug).lower()
    if target_service != cat.service_id or target_slug != cat.slug:
        clash = await session.exec(
            select(Category.id)
            .where(Category.service_id == target_service)
            .where(Category.slug == target_slug)
            .where(Category.id != cat.id)  # type: ignore[arg-type]
            .where(Category.is_active.is_(True))  # type: ignore[attr-defined]
        )
        if clash.first() is not None:
            detail = (
                "slug_exists_in_destination"
                if target_service != cat.service_id
                else "slug_exists"
            )
            raise HTTPException(status_code=409, detail=detail)

    cat.service_id = target_service
    cat.slug = target_slug
    if payload.image_url is not None:
        cat.image_url = payload.image_url
    if payload.sort_order is not None:
        cat.sort_order = payload.sort_order
    if payload.is_active is not None:
        cat.is_active = payload.is_active

    if payload.name is not None or payload.description is not None:
        existing_en = (await session.exec(
            select(CategoryTranslation).where(
                CategoryTranslation.category_id == cat.id,
                CategoryTranslation.language_code == _EN,
            )
        )).first()
        if existing_en is None:
            session.add(CategoryTranslation(
                category_id=cat.id,
                language_code=_EN,
                name=payload.name or cat.slug,
                description=payload.description,
            ))
        else:
            if payload.name is not None:
                existing_en.name = payload.name
            if payload.description is not None:
                existing_en.description = payload.description

    session.add(cat)
    await session.flush()
    all_trans = (await session.exec(
        select(CategoryTranslation).where(CategoryTranslation.category_id == cat.id)
    )).all()
    response = _category_admin_read(cat, list(all_trans))
    await session.commit()
    return response


@router.delete("/categories/{category_id}")
async def delete_category_admin(
    category_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    cat = await session.get(Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="not_found")
    cat.is_active = False
    session.add(cat)
    await session.commit()
    return {"detail": "deactivated"}


# ─── Subcategories ─────────────────────────────────────────────


def _subcategory_admin_read(
    sub: Subcategory, translations: Sequence[SubcategoryTranslation], child_count: int = 0
) -> SubcategoryAdminRead:
    assert sub.id is not None
    return SubcategoryAdminRead(
        id=sub.id,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
        category_id=sub.category_id,
        slug=sub.slug,
        name=_english_name(translations, sub.slug),
        description=_english_description(translations),
        image_url=sub.image_url,
        is_active=sub.is_active,
        sort_order=sub.sort_order,
        child_count=child_count,
        translations=_serialize_translations(translations),
    )


@router.get("/subcategories", response_model=PagedResponse[SubcategoryAdminRead])
async def list_subcategories_admin(
    category_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> PagedResponse[SubcategoryAdminRead]:
    stmt = select(Subcategory)
    if q:
        like = f"%{q.lower()}%"
        stmt = (
            stmt.outerjoin(
                SubcategoryTranslation,
                SubcategoryTranslation.subcategory_id == Subcategory.id,  # type: ignore[arg-type]
            )
            .where(
                or_(
                    Subcategory.slug.ilike(like),  # type: ignore[attr-defined]
                    SubcategoryTranslation.name.ilike(like),  # type: ignore[attr-defined]
                )
            )
            .distinct()
        )
    if category_id is not None:
        stmt = stmt.where(Subcategory.category_id == category_id)
    if is_active is not None:
        stmt = stmt.where(Subcategory.is_active == is_active)
    stmt = stmt.order_by(Subcategory.category_id, Subcategory.sort_order, Subcategory.id)  # type: ignore[arg-type]
    offset = (page - 1) * page_size

    total = int((await session.exec(select(func.count()).select_from(stmt.subquery()))).one())
    subs = list((await session.exec(stmt.offset(offset).limit(page_size))).all())
    ids = [s.id for s in subs if s.id is not None]
    trans = await load_subcategory_translations(session, ids)

    counts: dict[int, int] = {}
    if ids:
        active_for_children = _resolve_active_filter(is_active)
        prod_count_rows = (await session.exec(
            select(MasterProduct.subcategory_id, func.count())  # type: ignore[arg-type]
            .where(MasterProduct.subcategory_id.in_(ids))  # type: ignore[attr-defined]
            .where(MasterProduct.is_active == active_for_children)
            .group_by(MasterProduct.subcategory_id)  # type: ignore[arg-type]
        )).all()
        counts = {row[0]: row[1] for row in prod_count_rows}

    items = [
        _subcategory_admin_read(s, trans.get(s.id, []), counts.get(s.id, 0))
        for s in subs
        if s.id is not None
    ]
    return PagedResponse[SubcategoryAdminRead](
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/subcategories/{subcategory_id}", response_model=SubcategoryAdminRead)
async def get_subcategory_admin(
    subcategory_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> SubcategoryAdminRead:
    sub = await session.get(Subcategory, subcategory_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="not_found")
    trans = (await session.exec(
        select(SubcategoryTranslation).where(SubcategoryTranslation.subcategory_id == subcategory_id)
    )).all()
    return _subcategory_admin_read(sub, list(trans))


@router.post("/subcategories", response_model=SubcategoryAdminRead)
async def create_subcategory_admin(
    payload: SubcategoryCreate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> SubcategoryAdminRead:
    cat = await session.get(Category, payload.category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="parent_not_found")
    slug = (payload.slug or _slugify(payload.name)).lower()
    clash = await session.exec(
        select(Subcategory.id)
        .where(Subcategory.category_id == payload.category_id)
        .where(Subcategory.slug == slug)
        .where(Subcategory.is_active.is_(True))  # type: ignore[attr-defined]
    )
    if clash.first() is not None:
        raise HTTPException(status_code=409, detail="slug_exists")
    sub = Subcategory(
        category_id=payload.category_id,
        slug=slug,
        image_url=payload.image_url,
        is_active=True,
        sort_order=payload.sort_order,
    )
    session.add(sub)
    await session.flush()
    assert sub.id is not None
    en = SubcategoryTranslation(
        subcategory_id=sub.id,
        language_code=_EN,
        name=payload.name,
        description=payload.description,
    )
    session.add(en)
    await session.flush()
    response = _subcategory_admin_read(sub, [en], 0)
    await session.commit()
    return response


@router.put("/subcategories/{subcategory_id}", response_model=SubcategoryAdminRead)
async def update_subcategory_admin(  # noqa: C901
    subcategory_id: int,
    payload: SubcategoryUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> SubcategoryAdminRead:
    sub = await session.get(Subcategory, subcategory_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="not_found")

    target_cat = sub.category_id
    if payload.category_id is not None and payload.category_id != sub.category_id:
        parent = await session.get(Category, payload.category_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="parent_not_found")
        target_cat = payload.category_id

    target_slug = (payload.slug or sub.slug).lower()
    if target_cat != sub.category_id or target_slug != sub.slug:
        clash = await session.exec(
            select(Subcategory.id)
            .where(Subcategory.category_id == target_cat)
            .where(Subcategory.slug == target_slug)
            .where(Subcategory.id != sub.id)  # type: ignore[arg-type]
            .where(Subcategory.is_active.is_(True))  # type: ignore[attr-defined]
        )
        if clash.first() is not None:
            detail = (
                "slug_exists_in_destination" if target_cat != sub.category_id else "slug_exists"
            )
            raise HTTPException(status_code=409, detail=detail)

    sub.category_id = target_cat
    sub.slug = target_slug
    if payload.image_url is not None:
        sub.image_url = payload.image_url
    if payload.sort_order is not None:
        sub.sort_order = payload.sort_order
    if payload.is_active is not None:
        sub.is_active = payload.is_active

    if payload.name is not None or payload.description is not None:
        existing_en = (await session.exec(
            select(SubcategoryTranslation).where(
                SubcategoryTranslation.subcategory_id == sub.id,
                SubcategoryTranslation.language_code == _EN,
            )
        )).first()
        if existing_en is None:
            session.add(SubcategoryTranslation(
                subcategory_id=sub.id,
                language_code=_EN,
                name=payload.name or sub.slug,
                description=payload.description,
            ))
        else:
            if payload.name is not None:
                existing_en.name = payload.name
            if payload.description is not None:
                existing_en.description = payload.description

    session.add(sub)
    await session.flush()
    all_trans = (await session.exec(
        select(SubcategoryTranslation).where(SubcategoryTranslation.subcategory_id == sub.id)
    )).all()
    response = _subcategory_admin_read(sub, list(all_trans))
    await session.commit()
    return response


@router.delete("/subcategories/{subcategory_id}")
async def delete_subcategory_admin(
    subcategory_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    sub = await session.get(Subcategory, subcategory_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="not_found")
    sub.is_active = False
    session.add(sub)
    await session.commit()
    return {"detail": "deactivated"}


# ─── Products ──────────────────────────────────────────────────


def _image_read(row: MasterProductImage) -> ProductImageRead:
    assert row.id is not None
    return ProductImageRead(id=row.id, url=row.url, source=row.source, position=row.position)


def _product_admin_read(
    p: MasterProduct,
    translations: Sequence[MasterProductTranslation],
    images: Sequence[MasterProductImage] = (),
) -> ProductAdminRead:
    assert p.id is not None
    return ProductAdminRead(
        id=p.id,
        created_at=p.created_at,
        updated_at=p.updated_at,
        subcategory_id=p.subcategory_id,
        slug=p.slug,
        name=_english_name(translations, p.slug),
        description=_english_description(translations) or "",
        image_url=p.image_url,
        base_price=p.base_price,
        brand=p.brand,
        unit=p.unit,
        is_active=p.is_active,
        images=[_image_read(i) for i in images],
        translations=_serialize_translations(translations),
    )


@router.get("/products", response_model=PagedResponse[ProductAdminRead])
async def list_products_admin(
    subcategory_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> PagedResponse[ProductAdminRead]:
    stmt = select(MasterProduct)
    if q:
        like = f"%{q.lower()}%"
        stmt = (
            stmt.outerjoin(
                MasterProductTranslation,
                MasterProductTranslation.master_product_id == MasterProduct.id,  # type: ignore[arg-type]
            )
            .where(
                or_(
                    MasterProduct.slug.ilike(like),  # type: ignore[attr-defined]
                    MasterProductTranslation.name.ilike(like),  # type: ignore[attr-defined]
                )
            )
            .distinct()
        )
    if subcategory_id is not None:
        stmt = stmt.where(MasterProduct.subcategory_id == subcategory_id)
    if is_active is not None:
        stmt = stmt.where(MasterProduct.is_active == is_active)
    stmt = stmt.order_by(MasterProduct.subcategory_id, MasterProduct.id)  # type: ignore[arg-type]
    offset = (page - 1) * page_size

    total = int((await session.exec(select(func.count()).select_from(stmt.subquery()))).one())
    prods = list((await session.exec(stmt.offset(offset).limit(page_size))).all())
    ids = [p.id for p in prods if p.id is not None]
    trans = await load_product_translations(session, ids)
    items = [
        _product_admin_read(p, trans.get(p.id, []))
        for p in prods
        if p.id is not None
    ]
    return PagedResponse[ProductAdminRead](
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/products/{product_id}", response_model=ProductAdminRead)
async def get_product_admin(
    product_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ProductAdminRead:
    prod = await session.get(MasterProduct, product_id)
    if prod is None:
        raise HTTPException(status_code=404, detail="not_found")
    trans = (await session.exec(
        select(MasterProductTranslation).where(MasterProductTranslation.master_product_id == product_id)
    )).all()
    images = await product_image_svc.list_images(session, product_id)
    return _product_admin_read(prod, list(trans), images)


@router.post("/products", response_model=ProductAdminRead)
async def create_product_admin(
    payload: ProductAdminCreate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ProductAdminRead:
    sub = await session.get(Subcategory, payload.subcategory_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="parent_not_found")
    slug = (payload.slug or _slugify(payload.name)).lower()
    clash = await session.exec(
        select(MasterProduct.id)
        .where(MasterProduct.subcategory_id == payload.subcategory_id)
        .where(MasterProduct.slug == slug)
        .where(MasterProduct.is_active.is_(True))  # type: ignore[attr-defined]
    )
    if clash.first() is not None:
        raise HTTPException(status_code=409, detail="slug_exists")
    prod = MasterProduct(
        subcategory_id=payload.subcategory_id,
        slug=slug,
        image_url=payload.image_url,
        base_price=payload.base_price,
        brand=payload.brand,
        unit=payload.unit,
        is_active=True,
    )
    session.add(prod)
    await session.flush()
    assert prod.id is not None
    en = MasterProductTranslation(
        master_product_id=prod.id,
        language_code=_EN,
        name=payload.name,
        description=payload.description,
    )
    session.add(en)
    # Seed image row 0 from the create-time image_url so the image collection
    # (the single source of truth for the cover) and the image_url cover cache
    # agree from the start — otherwise the first image added later would
    # silently replace this cover. See spec §6.
    if payload.image_url:
        session.add(
            MasterProductImage(
                master_product_id=prod.id,
                position=0,
                url=payload.image_url,
                source="external",
                storage_key=None,
            )
        )
    await session.flush()
    images = await product_image_svc.list_images(session, prod.id)
    response = _product_admin_read(prod, [en], images)
    await session.commit()
    return response


@router.put("/products/{product_id}", response_model=ProductAdminRead)
async def update_product_admin(  # noqa: C901
    product_id: int,
    payload: ProductAdminUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ProductAdminRead:
    prod = await session.get(MasterProduct, product_id)
    if prod is None:
        raise HTTPException(status_code=404, detail="not_found")

    target_sub = prod.subcategory_id
    if payload.subcategory_id is not None and payload.subcategory_id != prod.subcategory_id:
        parent = await session.get(Subcategory, payload.subcategory_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="parent_not_found")
        target_sub = payload.subcategory_id

    target_slug = (payload.slug or prod.slug).lower()
    if target_sub != prod.subcategory_id or target_slug != prod.slug:
        clash = await session.exec(
            select(MasterProduct.id)
            .where(MasterProduct.subcategory_id == target_sub)
            .where(MasterProduct.slug == target_slug)
            .where(MasterProduct.id != prod.id)  # type: ignore[arg-type]
            .where(MasterProduct.is_active.is_(True))  # type: ignore[attr-defined]
        )
        if clash.first() is not None:
            detail = (
                "slug_exists_in_destination"
                if target_sub != prod.subcategory_id
                else "slug_exists"
            )
            raise HTTPException(status_code=409, detail=detail)

    prod.subcategory_id = target_sub
    prod.slug = target_slug
    # NOTE: image_url is owned by the image collection (see product image
    # endpoints below); it is intentionally NOT writable via this update.
    if payload.base_price is not None:
        prod.base_price = payload.base_price
    if payload.brand is not None:
        prod.brand = payload.brand
    if payload.unit is not None:
        prod.unit = payload.unit
    if payload.is_active is not None:
        prod.is_active = payload.is_active

    if payload.name is not None or payload.description is not None:
        existing_en = (await session.exec(
            select(MasterProductTranslation).where(
                MasterProductTranslation.master_product_id == prod.id,
                MasterProductTranslation.language_code == _EN,
            )
        )).first()
        if existing_en is None:
            session.add(MasterProductTranslation(
                master_product_id=prod.id,
                language_code=_EN,
                name=payload.name or prod.slug,
                description=payload.description or "",
            ))
        else:
            if payload.name is not None:
                existing_en.name = payload.name
            if payload.description is not None:
                existing_en.description = payload.description

    session.add(prod)
    await session.flush()
    all_trans = (await session.exec(
        select(MasterProductTranslation).where(
            MasterProductTranslation.master_product_id == prod.id
        )
    )).all()
    response = _product_admin_read(prod, list(all_trans))
    await session.commit()
    return response


@router.delete("/products/{product_id}")
async def delete_product_admin(
    product_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    prod = await session.get(MasterProduct, product_id)
    if prod is None:
        raise HTTPException(status_code=404, detail="not_found")
    prod.is_active = False
    session.add(prod)
    await session.commit()
    return {"detail": "deactivated"}


# ─── Translation upsert ────────────────────────────────────────


def _validate_language(code: str) -> None:
    if code not in _VALID_LANGS:
        raise HTTPException(status_code=400, detail="unknown_language")


async def _upsert_translation(
    session: AsyncSession,
    *,
    model: Type,
    fk_field: str,
    entity_id: int,
    payload: TranslationUpsert,
) -> None:
    _validate_language(payload.language_code)
    description_value = payload.description or ""
    is_empty = not payload.name.strip() and not description_value.strip()
    fk_attr = getattr(model, fk_field)
    lang_attr = model.language_code  # noqa: B009 — model arg shape varies per entity
    existing_q = await session.exec(
        select(model)
        .where(fk_attr == entity_id)
        .where(lang_attr == payload.language_code)
    )
    existing = existing_q.first()
    if existing is not None:
        if is_empty:
            await session.delete(existing)
        else:
            existing.name = payload.name
            existing.description = description_value
        return
    if is_empty:
        return
    kwargs = {
        fk_field: entity_id,
        "language_code": payload.language_code,
        "name": payload.name,
        "description": description_value,
    }
    session.add(model(**kwargs))


@router.post("/services/{service_id}/translations")
async def upsert_service_translation(
    service_id: int,
    payload: TranslationUpsert,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    svc = await session.get(Service, service_id)
    if svc is None:
        raise HTTPException(status_code=404, detail="not_found")
    await _upsert_translation(
        session,
        model=ServiceTranslation,
        fk_field="service_id",
        entity_id=service_id,
        payload=payload,
    )
    await session.commit()
    return {"detail": "ok"}


@router.post("/categories/{category_id}/translations")
async def upsert_category_translation(
    category_id: int,
    payload: TranslationUpsert,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    cat = await session.get(Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="not_found")
    await _upsert_translation(
        session,
        model=CategoryTranslation,
        fk_field="category_id",
        entity_id=category_id,
        payload=payload,
    )
    await session.commit()
    return {"detail": "ok"}


@router.post("/subcategories/{subcategory_id}/translations")
async def upsert_subcategory_translation(
    subcategory_id: int,
    payload: TranslationUpsert,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    sub = await session.get(Subcategory, subcategory_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="not_found")
    await _upsert_translation(
        session,
        model=SubcategoryTranslation,
        fk_field="subcategory_id",
        entity_id=subcategory_id,
        payload=payload,
    )
    await session.commit()
    return {"detail": "ok"}


@router.post("/products/{product_id}/translations")
async def upsert_product_translation(
    product_id: int,
    payload: TranslationUpsert,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    prod = await session.get(MasterProduct, product_id)
    if prod is None:
        raise HTTPException(status_code=404, detail="not_found")
    await _upsert_translation(
        session,
        model=MasterProductTranslation,
        fk_field="master_product_id",
        entity_id=product_id,
        payload=payload,
    )
    await session.commit()
    return {"detail": "ok"}


# ─── Product images ────────────────────────────────────────────


@router.post("/products/{product_id}/images/upload", response_model=ProductImageRead)
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ProductImageRead:
    raw = await file.read()
    try:
        row = await product_image_svc.add_uploaded_image(session, product_id, raw)
    except product_image_svc.ProductNotFound:
        raise HTTPException(status_code=404, detail="not_found") from None
    except product_image_svc.ProductImageLimitError:
        raise HTTPException(status_code=409, detail="image_limit_reached") from None
    except ImageValidationError as exc:
        code = str(exc)
        status = 413 if code == "file_too_large" else 422
        raise HTTPException(status_code=status, detail=code) from exc
    return _image_read(row)


@router.post("/products/{product_id}/images/url", response_model=ProductImageRead)
async def add_product_image_url(
    product_id: int,
    payload: ProductImageUrlCreate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ProductImageRead:
    try:
        row = await product_image_svc.add_external_image(session, product_id, payload.url)
    except product_image_svc.ProductNotFound:
        raise HTTPException(status_code=404, detail="not_found") from None
    except product_image_svc.ProductImageLimitError:
        raise HTTPException(status_code=409, detail="image_limit_reached") from None
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _image_read(row)


@router.patch("/products/{product_id}/images/order", response_model=List[ProductImageRead])
async def reorder_product_images(
    product_id: int,
    payload: ProductImageReorder,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> List[ProductImageRead]:
    try:
        rows = await product_image_svc.reorder_images(session, product_id, payload.image_ids)
    except product_image_svc.ProductNotFound:
        raise HTTPException(status_code=404, detail="not_found") from None
    except product_image_svc.ProductImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [_image_read(r) for r in rows]


@router.delete("/products/{product_id}/images/{image_id}")
async def delete_product_image(
    product_id: int,
    image_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    try:
        await product_image_svc.delete_image(session, product_id, image_id)
    except product_image_svc.ProductImageNotFound:
        raise HTTPException(status_code=404, detail="not_found") from None
    return {"detail": "deleted"}
