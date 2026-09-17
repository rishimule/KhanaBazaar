# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Shared CSV builders for the catalog bulk-import test modules.

Not a test module itself (no `test_` prefix) — pytest collects nothing here.
"""

import csv
import io
from typing import Any, Dict, List, Optional

from httpx import AsyncClient

from app.services.catalog_csv import ALL_COLUMNS

IMPORTS = "/api/v1/catalog/admin/imports"

BASE_ROW: Dict[str, Any] = {
    "service_slug": "grocery",
    "service_name": "Grocery",
    "category_slug": "fruits",
    "category_name": "Fruits",
    "subcategory_slug": "fresh-fruits",
    "subcategory_name": "Fresh Fruits",
    "product_slug": "banana-1kg",
    "product_name": "Banana 1kg",
    "base_price": "60",
}


def row(**overrides: Any) -> Dict[str, Any]:
    return {**BASE_ROW, **overrides}


def build_csv(
    rows: List[Dict[str, Any]], columns: Optional[List[str]] = None
) -> bytes:
    fieldnames = columns or list(ALL_COLUMNS)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for record in rows:
        writer.writerow({k: record.get(k, "") for k in fieldnames})
    return buf.getvalue().encode("utf-8")


async def upload(
    client: AsyncClient,
    headers: Dict[str, str],
    rows: List[Dict[str, Any]],
    *,
    raw: Optional[bytes] = None,
    filename: str = "catalog.csv",
) -> Any:
    """POST a CSV to the import endpoint and return the httpx response."""
    payload = raw if raw is not None else build_csv(rows)
    return await client.post(
        IMPORTS,
        headers=headers,
        files={"file": (filename, payload, "text/csv")},
    )


async def upload_and_apply(
    client: AsyncClient,
    headers: Dict[str, str],
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Full two-phase run. Returns the job as of after Apply."""
    created = await upload(client, headers, rows)
    assert created.status_code == 200, created.text
    job_id = created.json()["id"]
    applied = await client.post(f"{IMPORTS}/{job_id}/apply", headers=headers)
    assert applied.status_code == 200, applied.text
    return dict(applied.json())


def counts(plan: Dict[str, Any], level: str) -> Dict[str, int]:
    return {k: int(v) for k, v in plan[level].items()}
