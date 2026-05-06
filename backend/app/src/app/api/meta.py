from fastapi import APIRouter

from app.core.config import settings
from app.core.indian_states import INDIAN_STATES

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe under the versioned API prefix.

    Mirrors the root `/health` route. Both are kept: the root path serves
    legacy uptime probes and load-balancer health checks; the versioned
    path lets API consumers verify reachability without crossing the API
    prefix boundary.
    """
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@router.get("/indian-states")
async def get_indian_states() -> dict[str, list[str]]:
    return {"states": INDIAN_STATES}
