# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
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
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
