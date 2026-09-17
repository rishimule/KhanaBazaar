# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Phase 1 of the bulk import: upload validates, plans and stages.

The load-bearing property here is that upload writes **nothing** to the
catalog — "preview" has to be a guarantee, not a hint.
"""

import pytest
from httpx import AsyncClient
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Category, MasterProduct, Service, Subcategory
from tests.catalog_csv_fixtures import IMPORTS, build_csv, counts, row, upload


async def _catalog_size(session: AsyncSession) -> tuple[int, int, int, int]:
    out = []
    for model in (Service, Category, Subcategory, MasterProduct):
        total = (await session.exec(select(func.count()).select_from(model))).one()
        out.append(int(total))
    return tuple(out)  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_upload_plans_creates_without_writing_anything(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    before = await _catalog_size(session)

    r = await upload(
        client,
        admin_auth_headers,
        [row(product_slug="banana-1kg"), row(product_slug="apple-1kg")],
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["status"] == "validated"
    assert body["total_rows"] == 2
    assert body["error_rows"] == 0
    assert body["applied"] is None
    assert body["filename"] == "catalog.csv"

    # Distinct paths, not rows: one service/category/subcategory, two products.
    assert counts(body["plan"], "service") == {"create": 1, "update": 0, "noop": 0}
    assert counts(body["plan"], "category") == {"create": 1, "update": 0, "noop": 0}
    assert counts(body["plan"], "subcategory") == {"create": 1, "update": 0, "noop": 0}
    assert counts(body["plan"], "product") == {"create": 2, "update": 0, "noop": 0}

    assert await _catalog_size(session) == before


@pytest.mark.asyncio
async def test_upload_stages_every_row_with_per_level_verdicts(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    created = await upload(client, admin_auth_headers, [row()])
    job_id = created.json()["id"]

    r = await client.get(f"{IMPORTS}/{job_id}/rows", headers=admin_auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    staged = body["items"][0]
    assert staged["line_number"] == 1
    assert staged["action"] == "create"
    assert staged["level_plan"] == {
        "service": "create",
        "category": "create",
        "subcategory": "create",
        "product": "create",
    }
    assert staged["errors"] == []
    assert staged["applied_at"] is None


@pytest.mark.asyncio
async def test_bad_rows_are_staged_not_rejected(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    """One bad line must not cost the operator the other 2,999."""
    created = await upload(
        client,
        admin_auth_headers,
        [
            row(product_slug="good-1"),
            row(product_slug="bad-1", base_price="-3"),
            row(product_slug="good-2"),
        ],
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["total_rows"] == 3
    assert body["error_rows"] == 1
    assert counts(body["plan"], "product")["create"] == 2

    job_id = body["id"]
    r = await client.get(
        f"{IMPORTS}/{job_id}/rows?only_errors=true", headers=admin_auth_headers
    )
    assert r.json()["total"] == 1
    bad = r.json()["items"][0]
    assert bad["line_number"] == 2
    assert bad["action"] == "error"
    assert bad["errors"][0]["column"] == "base_price"
    assert bad["errors"][0]["code"] == "price_invalid"


@pytest.mark.asyncio
async def test_missing_columns_is_a_422_with_the_column_list(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    raw = build_csv([row()], columns=["service_slug", "service_name"])
    r = await upload(client, admin_auth_headers, [], raw=raw)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "missing_columns"
    assert "base_price" in detail["columns"]


@pytest.mark.asyncio
async def test_empty_file_is_422(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    r = await upload(client, admin_auth_headers, [], raw=build_csv([]))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "empty_file"


@pytest.mark.asyncio
async def test_oversize_file_is_413(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    r = await upload(
        client, admin_auth_headers, [], raw=b"x" * (5 * 1024 * 1024 + 1)
    )
    assert r.status_code == 413
    assert r.json()["detail"]["code"] == "file_too_large"


@pytest.mark.asyncio
async def test_a_rejected_file_stages_no_job(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    await upload(client, admin_auth_headers, [], raw=build_csv([]))
    r = await client.get(IMPORTS, headers=admin_auth_headers)
    assert r.json()["total"] == 0


@pytest.mark.asyncio
async def test_plan_reports_noop_and_update_against_live_catalog(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    """Second upload of the same file plans noop; a changed price plans update."""
    first = await upload(client, admin_auth_headers, [row()])
    job_id = first.json()["id"]
    assert (
        await client.post(f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers)
    ).status_code == 200

    same = await upload(client, admin_auth_headers, [row()])
    plan = same.json()["plan"]
    assert counts(plan, "service")["noop"] == 1
    assert counts(plan, "category")["noop"] == 1
    assert counts(plan, "subcategory")["noop"] == 1
    assert counts(plan, "product")["noop"] == 1
    assert same.json()["total_rows"] == 1

    changed = await upload(client, admin_auth_headers, [row(base_price="75")])
    assert counts(changed.json()["plan"], "product")["update"] == 1
    # The staged row's headline action escalates to the deepest change.
    rows = await client.get(
        f"{IMPORTS}/{changed.json()['id']}/rows", headers=admin_auth_headers
    )
    assert rows.json()["items"][0]["action"] == "update"


@pytest.mark.asyncio
async def test_job_list_is_newest_first(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    await upload(client, admin_auth_headers, [row()], filename="one.csv")
    await upload(client, admin_auth_headers, [row()], filename="two.csv")
    r = await client.get(IMPORTS, headers=admin_auth_headers)
    body = r.json()
    assert body["total"] == 2
    assert [i["filename"] for i in body["items"]] == ["two.csv", "one.csv"]


@pytest.mark.asyncio
async def test_unknown_job_is_404(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    assert (
        await client.get(f"{IMPORTS}/999999", headers=admin_auth_headers)
    ).status_code == 404
    assert (
        await client.get(f"{IMPORTS}/999999/rows", headers=admin_auth_headers)
    ).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/v1/catalog/admin/imports"),
        ("get", "/api/v1/catalog/admin/imports"),
        ("get", "/api/v1/catalog/admin/imports/template.csv"),
        ("get", "/api/v1/catalog/admin/export.csv"),
        ("post", "/api/v1/catalog/admin/bulk/status"),
    ],
)
async def test_bulk_endpoints_reject_anonymous(
    client: AsyncClient, method: str, path: str
) -> None:
    r = await getattr(client, method)(path)
    assert r.status_code in (401, 403), r.text


@pytest.mark.asyncio
async def test_template_downloads_as_csv(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    r = await client.get(f"{IMPORTS}/template.csv", headers=admin_auth_headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.text.splitlines()[0].startswith("service_slug,service_name")


@pytest.mark.asyncio
async def test_template_round_trips_through_upload(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    """The file we hand the operator must import cleanly as-is."""
    template = await client.get(f"{IMPORTS}/template.csv", headers=admin_auth_headers)
    r = await upload(
        client, admin_auth_headers, [], raw=template.text.encode("utf-8")
    )
    assert r.status_code == 200, r.text
    assert r.json()["error_rows"] == 0
