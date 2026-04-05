from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.base import User
from app.models.catalog import Category, MasterProduct

router = APIRouter()

@router.get("/categories", response_model=List[Category])
async def list_categories(session: AsyncSession = Depends(get_db_session)) -> List[Category]:
    result = await session.exec(select(Category))
    return list(result.all())

@router.post("/categories", response_model=Category)
async def create_category(
    category: Category,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin)
) -> Category:
    # Ensure ID doesn't conflict
    category.id = None
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category

@router.get("/products", response_model=List[MasterProduct])
async def list_products(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session)
) -> List[MasterProduct]:
    result = await session.exec(select(MasterProduct).offset(skip).limit(limit))
    return list(result.all())

@router.post("/products", response_model=MasterProduct)
async def create_product(
    product: MasterProduct,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin)
) -> MasterProduct:
    product.id = None

    # Verify category exists
    cat_check = await session.exec(select(Category).where(Category.id == product.category_id))
    if not cat_check.first():
        raise HTTPException(status_code=400, detail="Category does not exist")

    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product
