# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from pydantic import BaseModel


class ReconcileSummaryOut(BaseModel):
    finished_at: float | None = None
    mode: str | None = None
    deltas: dict[str, int] | None = None
    error: str | None = None


class IndexHealth(BaseModel):
    db_count: int
    meili_count: int
    db_max_updated_at: int
    meili_max_db_updated_at: int
    lag_seconds: int
    last_reconcile: ReconcileSummaryOut | None
    dlq_size: int
    meili_unreachable: bool = False


class SearchTermsHealth(BaseModel):
    db_count: int
    meili_count: int
    meili_unreachable: bool = False


class SearchHealthResponse(BaseModel):
    products: IndexHealth
    stores: IndexHealth
    search_terms: SearchTermsHealth
