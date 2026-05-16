# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel


class SearchQueryLog(SQLModel, table=True):
    __tablename__ = "search_query_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    query_id: UUID = Field(unique=True, nullable=False, index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", nullable=True)
    session_id: Optional[str] = Field(default=None, max_length=64, nullable=True)
    query: str = Field(nullable=False, max_length=100)
    locale: str = Field(nullable=False, max_length=8)
    lat: Optional[float] = Field(default=None, nullable=True)
    lng: Optional[float] = Field(default=None, nullable=True)
    store_id: Optional[int] = Field(default=None, foreign_key="store.id", nullable=True)
    result_count: int = Field(nullable=False)
    clicked_product_id: Optional[int] = Field(default=None, nullable=True)
    clicked_store_id: Optional[int] = Field(default=None, nullable=True)
    clicked_position: Optional[int] = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)
