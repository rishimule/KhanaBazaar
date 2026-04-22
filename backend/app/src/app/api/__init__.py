from fastapi import APIRouter

from app.api import auth, catalog, meta, sellers, stores, tasks

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
api_router.include_router(stores.router, prefix="/stores", tags=["stores"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(sellers.router, prefix="/sellers", tags=["sellers"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
