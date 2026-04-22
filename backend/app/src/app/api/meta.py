from fastapi import APIRouter

from app.core.indian_states import INDIAN_STATES

router = APIRouter()


@router.get("/indian-states")
async def get_indian_states() -> dict[str, list[str]]:
    return {"states": INDIAN_STATES}
