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
)

router = APIRouter()

_DEFAULT_SERVICE_SLUG = "default"
_DEFAULT_SUBCATEGORY_SLUG = "_default"
_EN = "en"


class CategoryRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    name: str
    description: str | None = None


class CategoryCreate(BaseModel):
    name: str
    description: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ProductRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    name: str
    description: str
    category_id: int
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
            name="Default",
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


async def _english_category_translation(
    session: AsyncSession, category_id: int
) -> CategoryTranslation | None:
    result = await session.exec(
        select(CategoryTranslation).where(
            CategoryTranslation.category_id == category_id,
            CategoryTranslation.language_code == _EN,
        )
    )
    return result.first()


async def _english_product_translation(
    session: AsyncSession, product_id: int
) -> MasterProductTranslation | None:
    result = await session.exec(
        select(MasterProductTranslation).where(
            MasterProductTranslation.master_product_id == product_id,
            MasterProductTranslation.language_code == _EN,
        )
    )
    return result.first()


def _category_read(category: Category, translation: CategoryTranslation | None) -> CategoryRead:
    assert category.id is not None
    return CategoryRead(
        id=category.id,
        created_at=category.created_at,
        updated_at=category.updated_at,
        name=translation.name if translation else category.slug,
        description=translation.description if translation else None,
    )


def _product_read(
    product: MasterProduct,
    translation: MasterProductTranslation | None,
    subcategory: Subcategory,
) -> ProductRead:
    assert product.id is not None
    return ProductRead(
        id=product.id,
        created_at=product.created_at,
        updated_at=product.updated_at,
        name=translation.name if translation else product.slug,
        description=translation.description if translation else "",
        category_id=subcategory.category_id,
        image_url=product.image_url,
        base_price=product.base_price,
    )


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
    translation = await _english_category_translation(session, category_id)
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
        select(MasterProduct, MasterProductTranslation, Subcategory)
        .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
        .join(
            MasterProductTranslation,
            MasterProductTranslation.master_product_id == MasterProduct.id,  # type: ignore[arg-type]
            isouter=True,
        )
        .where(
            (MasterProductTranslation.language_code == _EN)
            | (MasterProductTranslation.id.is_(None))  # type: ignore[union-attr]
        )
        .offset(skip)
        .limit(limit)
    )
    result = await session.exec(stmt)
    return [
        _product_read(product, translation, subcategory)
        for product, translation, subcategory in result.all()
    ]


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

    translation = await _english_product_translation(session, product_id)
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
