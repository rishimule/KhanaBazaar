from fastapi import APIRouter

from app.api import (
    auth,
    carts,
    catalog,
    customers,
    meta,
    orders,
    sellers,
    stores,
    tasks,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
api_router.include_router(stores.router, prefix="/stores", tags=["stores"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(sellers.router, prefix="/sellers", tags=["sellers"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(carts.router, prefix="/carts", tags=["carts"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
