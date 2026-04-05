from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,  # Set to False in production
    future=True,
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency object for FastAPI endpoints."""
    async with AsyncSession(engine) as session:
        yield session
