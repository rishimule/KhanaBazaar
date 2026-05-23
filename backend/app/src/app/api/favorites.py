# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_customer
from app.db.session import get_db_session
from app.models.base import User
from app.models.profile import CustomerProfile
from app.schemas.favorites import (
    FavoriteAtStore,
    FavoriteIdsResponse,
    FavoritesGroupedResponse,
    FavoriteToggleResponse,
)
from app.services import favorites as favorites_service

router = APIRouter()


async def _customer_profile_id(session: AsyncSession, user: User) -> int:
    row = (
        await session.exec(
            select(CustomerProfile.id).where(CustomerProfile.user_id == user.id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="customer_profile_not_found")
    return int(row)


@router.post(
    "/{product_id}",
    response_model=FavoriteToggleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_favorite_route(
    product_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> FavoriteToggleResponse:
    profile_id = await _customer_profile_id(session, user)
    try:
        await favorites_service.add_favorite(session, profile_id, product_id)
    except ValueError as e:
        if str(e) == "product_not_found":
            raise HTTPException(status_code=404, detail="product_not_found") from e
        raise
    return FavoriteToggleResponse(favourited=True)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite_route(
    product_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> Response:
    profile_id = await _customer_profile_id(session, user)
    await favorites_service.remove_favorite(session, profile_id, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/ids", response_model=FavoriteIdsResponse)
async def list_favorite_ids_route(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> FavoriteIdsResponse:
    profile_id = await _customer_profile_id(session, user)
    ids = await favorites_service.list_favorite_ids(session, profile_id)
    return FavoriteIdsResponse(ids=ids)


@router.get("/", response_model=FavoritesGroupedResponse)
async def list_grouped_favorites_route(
    lat: float,
    lng: float,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> FavoritesGroupedResponse:
    profile_id = await _customer_profile_id(session, user)
    return await favorites_service.list_grouped_favorites(
        session, profile_id, lat, lng
    )


@router.get("/stores/{store_id}", response_model=list[FavoriteAtStore])
async def list_store_favorites_route(
    store_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_customer),
) -> list[FavoriteAtStore]:
    profile_id = await _customer_profile_id(session, user)
    return await favorites_service.list_store_favorites(
        session, profile_id, store_id
    )
