import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.base import User
from app.models.catalog import (
    Category,
    CategoryTranslation,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from app.schemas.services import ServicePayload

router = APIRouter()

_DEFAULT_SERVICE_SLUG = "grocery"
_DEFAULT_SERVICE_NAME = "Grocery"
_DEFAULT_SUBCATEGORY_SLUG = "_default"
_EN = "en"


class ServiceRead(ServicePayload):
    pass


class CategoryRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    name: str
    description: str | None = None
    service_id: int


class CategoryCreate(BaseModel):
    name: str
    description: str | None = None
    service_id: int | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class SubcategoryRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    name: str
    description: str | None = None
    category_id: int
    slug: str


class ProductRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    name: str
    description: str
    category_id: int
    subcategory_id: int
    subcategory_name: str
    image_url: str | None = None
    base_price: float


class ProductCreate(BaseModel):
    name: str
    description: str
    category_id: int
    base_price: float
    image_url: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    base_price: Optional[float] = None
    image_url: Optional[str] = None


def _slugify(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return base or "item"


async def _ensure_default_service(session: AsyncSession) -> Service:
    result = await session.exec(select(Service).where(Service.slug == _DEFAULT_SERVICE_SLUG))
    service = result.first()
    if service is not None:
        return service
    service = Service(slug=_DEFAULT_SERVICE_SLUG, is_active=True, sort_order=0)
    session.add(service)
    await session.flush()
    session.add(
        ServiceTranslation(
            service_id=service.id,
            language_code=_EN,
            name=_DEFAULT_SERVICE_NAME,
            description=None,
        )
    )
    return service


async def _ensure_default_subcategory(session: AsyncSession, category_id: int) -> Subcategory:
    result = await session.exec(
        select(Subcategory).where(
            Subcategory.category_id == category_id,
            Subcategory.slug == _DEFAULT_SUBCATEGORY_SLUG,
        )
    )
    sub = result.first()
    if sub is not None:
        return sub
    sub = Subcategory(category_id=category_id, slug=_DEFAULT_SUBCATEGORY_SLUG, sort_order=0)
    session.add(sub)
    await session.flush()
    return sub


async def _localized_category_translation(
    session: AsyncSession, category_id: int, lang: str
) -> CategoryTranslation | None:
    if lang != _EN:
        result = await session.exec(
            select(CategoryTranslation).where(
                CategoryTranslation.category_id == category_id,
                CategoryTranslation.language_code == lang,
            )
        )
        row = result.first()
        if row is not None:
            return row
    result = await session.exec(
        select(CategoryTranslation).where(
            CategoryTranslation.category_id == category_id,
            CategoryTranslation.language_code == _EN,
        )
    )
    return result.first()


async def _localized_product_translation(
    session: AsyncSession, product_id: int, lang: str
) -> MasterProductTranslation | None:
    if lang != _EN:
        result = await session.exec(
            select(MasterProductTranslation).where(
                MasterProductTranslation.master_product_id == product_id,
                MasterProductTranslation.language_code == lang,
            )
        )
        row = result.first()
        if row is not None:
            return row
    result = await session.exec(
        select(MasterProductTranslation).where(
            MasterProductTranslation.master_product_id == product_id,
            MasterProductTranslation.language_code == _EN,
        )
    )
    return result.first()


async def _localized_subcategory_translation(
    session: AsyncSession, subcategory_id: int, lang: str
) -> SubcategoryTranslation | None:
    if lang != _EN:
        result = await session.exec(
            select(SubcategoryTranslation).where(
                SubcategoryTranslation.subcategory_id == subcategory_id,
                SubcategoryTranslation.language_code == lang,
            )
        )
        row = result.first()
        if row is not None:
            return row
    result = await session.exec(
        select(SubcategoryTranslation).where(
            SubcategoryTranslation.subcategory_id == subcategory_id,
            SubcategoryTranslation.language_code == _EN,
        )
    )
    return result.first()


def _subcategory_name(subcategory: Subcategory, translation: SubcategoryTranslation | None) -> str:
    return translation.name if translation else subcategory.slug


def _subcategory_read(
    subcategory: Subcategory, translation: SubcategoryTranslation | None
) -> SubcategoryRead:
    assert subcategory.id is not None
    return SubcategoryRead(
        id=subcategory.id,
        created_at=subcategory.created_at,
        updated_at=subcategory.updated_at,
        name=_subcategory_name(subcategory, translation),
        description=translation.description if translation else None,
        category_id=subcategory.category_id,
        slug=subcategory.slug,
    )


def _category_read(category: Category, translation: CategoryTranslation | None) -> CategoryRead:
    assert category.id is not None
    return CategoryRead(
        id=category.id,
        created_at=category.created_at,
        updated_at=category.updated_at,
        name=translation.name if translation else category.slug,
        description=translation.description if translation else None,
        service_id=category.service_id,
    )


def _service_read(service: Service, translation: ServiceTranslation | None) -> ServiceRead:
    assert service.id is not None
    return ServiceRead(
        id=service.id,
        created_at=service.created_at,
        updated_at=service.updated_at,
        slug=service.slug,
        name=translation.name if translation else service.slug,
        description=translation.description if translation else None,
        is_active=service.is_active,
        sort_order=service.sort_order,
    )


def _product_read(
    product: MasterProduct,
    translation: MasterProductTranslation | None,
    subcategory: Subcategory,
    subcategory_translation: SubcategoryTranslation | None = None,
) -> ProductRead:
    assert product.id is not None
    assert subcategory.id is not None
    return ProductRead(
        id=product.id,
        created_at=product.created_at,
        updated_at=product.updated_at,
        name=translation.name if translation else product.slug,
        description=translation.description if translation else "",
        category_id=subcategory.category_id,
        subcategory_id=subcategory.id,
        subcategory_name=_subcategory_name(subcategory, subcategory_translation),
        image_url=product.image_url,
        base_price=product.base_price,
    )


# ─── Services ─────────────────────────────────────────────────


@router.get("/services", response_model=List[ServiceRead])
async def list_services(session: AsyncSession = Depends(get_db_session)) -> List[ServiceRead]:
    stmt = (
        select(Service, ServiceTranslation)
        .join(
            ServiceTranslation,
            ServiceTranslation.service_id == Service.id,  # type: ignore[arg-type]
            isouter=True,
        )
        .where(Service.is_active == True)  # noqa: E712
        .where(
            (ServiceTranslation.language_code == _EN)
            | (ServiceTranslation.id.is_(None))  # type: ignore[union-attr]
        )
        .order_by(Service.sort_order, Service.id)  # type: ignore[arg-type]
    )
    result = await session.exec(stmt)
    return [_service_read(service, translation) for service, translation in result.all()]


# ─── Categories ───────────────────────────────────────────────


@router.get("/categories", response_model=List[CategoryRead])
async def list_categories(session: AsyncSession = Depends(get_db_session)) -> List[CategoryRead]:
    stmt = (
        select(Category, CategoryTranslation)
        .join(
            CategoryTranslation,
            CategoryTranslation.category_id == Category.id,  # type: ignore[arg-type]
            isouter=True,
        )
        .where(
            (CategoryTranslation.language_code == _EN)
            | (CategoryTranslation.id.is_(None))  # type: ignore[union-attr]
        )
    )
    result = await session.exec(stmt)
    return [_category_read(category, translation) for category, translation in result.all()]


@router.post("/categories", response_model=CategoryRead)
async def create_category(
    payload: CategoryCreate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> CategoryRead:
    if payload.service_id is not None:
        service = await session.get(Service, payload.service_id)
        if service is None:
            raise HTTPException(status_code=400, detail="Service does not exist")
    else:
        service = await _ensure_default_service(session)
    slug = _slugify(payload.name)
    category = Category(service_id=service.id, slug=slug, sort_order=0)
    session.add(category)
    await session.flush()
    translation = CategoryTranslation(
        category_id=category.id,
        language_code=_EN,
        name=payload.name,
        description=payload.description,
    )
    session.add(translation)
    await session.flush()
    response = _category_read(category, translation)
    await session.commit()
    return response


@router.put("/categories/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> CategoryRead:
    cat = await session.get(Category, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    translation = await _localized_category_translation(session, category_id, _EN)
    if translation is None:
        translation = CategoryTranslation(
            category_id=cat.id,
            language_code=_EN,
            name=payload.name or cat.slug,
            description=payload.description,
        )
        session.add(translation)
    else:
        if payload.name is not None:
            translation.name = payload.name
        if payload.description is not None:
            translation.description = payload.description
    await session.flush()
    response = _category_read(cat, translation)
    await session.commit()
    return response


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    cat = await session.get(Category, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    await session.delete(cat)
    await session.commit()
    return {"detail": "Category deleted"}


# ─── Products ─────────────────────────────────────────────────


@router.get("/products", response_model=List[ProductRead])
async def list_products(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
) -> List[ProductRead]:
    stmt = (
        select(
            MasterProduct,
            MasterProductTranslation,
            Subcategory,
            SubcategoryTranslation,
        )
        .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
        .join(
            MasterProductTranslation,
            MasterProductTranslation.master_product_id == MasterProduct.id,  # type: ignore[arg-type]
            isouter=True,
        )
        .join(
            SubcategoryTranslation,
            SubcategoryTranslation.subcategory_id == Subcategory.id,  # type: ignore[arg-type]
            isouter=True,
        )
        .where(
            (MasterProductTranslation.language_code == _EN)
            | (MasterProductTranslation.id.is_(None))  # type: ignore[union-attr]
        )
        .where(
            (SubcategoryTranslation.language_code == _EN)
            | (SubcategoryTranslation.id.is_(None))  # type: ignore[union-attr]
        )
        .offset(skip)
        .limit(limit)
    )
    result = await session.exec(stmt)
    return [
        _product_read(product, translation, subcategory, subcategory_translation)
        for product, translation, subcategory, subcategory_translation in result.all()
    ]


@router.get("/subcategories", response_model=List[SubcategoryRead])
async def list_subcategories(
    session: AsyncSession = Depends(get_db_session),
) -> List[SubcategoryRead]:
    stmt = (
        select(Subcategory, SubcategoryTranslation)
        .join(
            SubcategoryTranslation,
            SubcategoryTranslation.subcategory_id == Subcategory.id,  # type: ignore[arg-type]
            isouter=True,
        )
        .where(
            (SubcategoryTranslation.language_code == _EN)
            | (SubcategoryTranslation.id.is_(None))  # type: ignore[union-attr]
        )
        .order_by(
            Subcategory.category_id,  # type: ignore[arg-type]
            Subcategory.sort_order,  # type: ignore[arg-type]
            Subcategory.id,  # type: ignore[arg-type]
        )
    )
    result = await session.exec(stmt)
    return [_subcategory_read(sub, translation) for sub, translation in result.all()]


@router.post("/products", response_model=ProductRead)
async def create_product(
    payload: ProductCreate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ProductRead:
    cat_check = await session.exec(select(Category).where(Category.id == payload.category_id))
    if not cat_check.first():
        raise HTTPException(status_code=400, detail="Category does not exist")
    subcategory = await _ensure_default_subcategory(session, payload.category_id)
    slug = _slugify(payload.name)
    product = MasterProduct(
        subcategory_id=subcategory.id,
        slug=slug,
        image_url=payload.image_url,
        base_price=payload.base_price,
    )
    session.add(product)
    await session.flush()
    translation = MasterProductTranslation(
        master_product_id=product.id,
        language_code=_EN,
        name=payload.name,
        description=payload.description,
    )
    session.add(translation)
    await session.flush()
    response = _product_read(product, translation, subcategory)
    await session.commit()
    return response


@router.put("/products/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ProductRead:
    product = await session.get(MasterProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if payload.category_id is not None:
        subcategory = await _ensure_default_subcategory(session, payload.category_id)
        assert subcategory.id is not None
        product.subcategory_id = subcategory.id
    else:
        sub_lookup = await session.get(Subcategory, product.subcategory_id)
        assert sub_lookup is not None
        subcategory = sub_lookup

    if payload.base_price is not None:
        product.base_price = payload.base_price
    if payload.image_url is not None:
        product.image_url = payload.image_url

    translation = await _localized_product_translation(session, product_id, _EN)
    if translation is None:
        translation = MasterProductTranslation(
            master_product_id=product.id,
            language_code=_EN,
            name=payload.name or product.slug,
            description=payload.description or "",
        )
        session.add(translation)
    else:
        if payload.name is not None:
            translation.name = payload.name
        if payload.description is not None:
            translation.description = payload.description

    session.add(product)
    await session.flush()
    response = _product_read(product, translation, subcategory)
    await session.commit()
    return response


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    product = await session.get(MasterProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await session.delete(product)
    await session.commit()
    return {"detail": "Product deleted"}
