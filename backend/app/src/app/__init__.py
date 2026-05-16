# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# CORS — origins driven by FRONTEND_ORIGIN env var (comma-separated)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "environment": settings.ENVIRONMENT}

from app.api import api_router  # noqa: E402

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
async def _search_startup() -> None:
    from app.search.bootstrap import ensure_indexes
    from app.search.client import get_meili_client
    try:
        await ensure_indexes(get_meili_client())
    except Exception as exc:  # noqa: BLE001
        # Meilisearch may be unavailable in some envs (e.g. CI without the service);
        # log and continue so the app still boots.
        import logging
        logging.getLogger(__name__).warning(
            "search.bootstrap.failed err=%s", exc,
        )


@app.on_event("shutdown")
async def _search_shutdown() -> None:
    from app.search.client import close_meili_client
    await close_meili_client()
