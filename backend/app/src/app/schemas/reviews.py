# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from pydantic import BaseModel, Field


class OrderReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class OrderReviewRead(BaseModel):
    rating: int
    comment: str | None
