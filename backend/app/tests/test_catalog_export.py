# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""CSV export, and the round-trip invariant that makes bulk EDITING possible.

The centrepiece is `test_unedited_export_reimports_as_all_noop`: export is the
only practical way to author a slug-keyed edit file, so if export and import
ever disagree about a column, every operator edit silently becomes a create.
"""

import csv
import io

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import MasterProduct, Service
from app.services.catalog_csv import ALL_COLUMNS
from tests.catalog_csv_fixtures import IMPORTS, counts, row, upload, upload_and_apply

pytestmark = pytest.mark.asyncio

EXPORT = "/api/v1/catalog/admin/export.csv"

_SEED = [
    row(
        product_slug="banana-1kg",
        product_description="Fresh robusta bananas",
        brand="Local Farm",
        unit="kg",
        service_description="Everyday groceries",
        category_description="Fresh produce",
        subcategory_description="Seasonal fruit",
        service_sort_order="2",
        category_sort_order="1",
        subcategory_sort_order="4",
        product_image_url="https://example.com/banana.jpg",
        product_name_hi="केला 1 किग्रा",
        product_desc_hi="ताज़े केले",
        base_price="60.50",
    ),
    row(product_slug="apple-1kg", product_name="Apple 1kg", base_price="200"),
    row(
        service_slug="pharmacy",
        service_name="Pharmacy",
        category_slug="otc",
        category_name="OTC",
        subcategory_slug="painkillers",
        subcategory_name="Painkillers",
        product_slug="paracetamol-500",
        product_name="Paracetamol 500mg",
        base_price="25",
    ),
]


def parse(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


async def test_export_header_matches_the_importer_exactly(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    r = await client.get(EXPORT, headers=admin_auth_headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.text.splitlines()[0].split(",") == list(ALL_COLUMNS)


async def test_export_of_an_empty_catalog_is_header_only(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    r = await client.get(EXPORT, headers=admin_auth_headers)
    assert parse(r.text) == []


async def test_export_emits_every_field(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    await upload_and_apply(client, admin_auth_headers, _SEED)
    records = parse((await client.get(EXPORT, headers=admin_auth_headers)).text)
    by_slug = {r["product_slug"]: r for r in records}
    assert set(by_slug) == {"banana-1kg", "apple-1kg", "paracetamol-500"}

    banana = by_slug["banana-1kg"]
    assert banana["service_slug"] == "grocery"
    assert banana["service_name"] == "Grocery"
    assert banana["service_description"] == "Everyday groceries"
    assert banana["service_sort_order"] == "2"
    assert banana["category_description"] == "Fresh produce"
    assert banana["subcategory_sort_order"] == "4"
    assert banana["product_name"] == "Banana 1kg"
    assert banana["product_description"] == "Fresh robusta bananas"
    assert banana["base_price"] == "60.5"
    assert banana["brand"] == "Local Farm"
    assert banana["unit"] == "kg"
    assert banana["product_image_url"] == "https://example.com/banana.jpg"
    assert banana["product_name_hi"] == "केला 1 किग्रा"
    assert banana["product_desc_hi"] == "ताज़े केले"
    # Languages with no translation come back blank, not missing.
    assert banana["product_name_gu"] == ""


async def test_unedited_export_reimports_as_all_noop(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """The invariant the whole edit workflow rests on."""
    await upload_and_apply(client, admin_auth_headers, _SEED)
    exported = (await client.get(EXPORT, headers=admin_auth_headers)).text

    reimported = await upload(
        client, admin_auth_headers, [], raw=exported.encode("utf-8")
    )
    assert reimported.status_code == 200, reimported.text
    body = reimported.json()
    assert body["error_rows"] == 0
    plan = body["plan"]
    for level in ("service", "category", "subcategory", "product"):
        assert counts(plan, level)["create"] == 0, f"{level} planned a create"
        assert counts(plan, level)["update"] == 0, f"{level} planned an update"
        assert counts(plan, level)["noop"] > 0, f"{level} planned nothing"

    # And applying it changes nothing.
    applied = await client.post(
        f"{IMPORTS}/{body['id']}/apply", headers=admin_auth_headers
    )
    assert applied.status_code == 200
    assert len((await session.exec(select(MasterProduct))).all()) == 3


async def test_edited_export_updates_in_place(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """Export → edit one cell → re-import is the bulk-edit workflow."""
    await upload_and_apply(client, admin_auth_headers, _SEED)
    exported = (await client.get(EXPORT, headers=admin_auth_headers)).text

    records = parse(exported)
    for record in records:
        if record["product_slug"] == "apple-1kg":
            record["base_price"] = "222"
            record["brand"] = "Orchard Co"
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(ALL_COLUMNS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)

    job = await upload(
        client, admin_auth_headers, [], raw=buf.getvalue().encode("utf-8")
    )
    assert counts(job.json()["plan"], "product") == {
        "create": 0,
        "update": 1,
        "noop": 2,
    }
    await client.post(f"{IMPORTS}/{job.json()['id']}/apply", headers=admin_auth_headers)

    apple = (
        await session.exec(
            select(MasterProduct).where(MasterProduct.slug == "apple-1kg")
        )
    ).first()
    assert apple is not None
    await session.refresh(apple)
    assert apple.base_price == pytest.approx(222.0)
    assert apple.brand == "Orchard Co"


@pytest.mark.parametrize("price", ["0.01", "1", "99.99", "1234.5", "999999"])
async def test_price_formatting_round_trips(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    price: str,
) -> None:
    """`_format_price` is used on both sides of the diff, so any stored value
    must re-import as a noop rather than an endless update."""
    await upload_and_apply(client, admin_auth_headers, [row(base_price=price)])
    exported = (await client.get(EXPORT, headers=admin_auth_headers)).text
    again = await upload(client, admin_auth_headers, [], raw=exported.encode("utf-8"))
    assert counts(again.json()["plan"], "product")["noop"] == 1


async def test_export_filters_by_service(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    await upload_and_apply(client, admin_auth_headers, _SEED)
    grocery = (
        await session.exec(select(Service).where(Service.slug == "grocery"))
    ).first()
    assert grocery is not None

    r = await client.get(
        f"{EXPORT}?service_id={grocery.id}", headers=admin_auth_headers
    )
    slugs = {rec["product_slug"] for rec in parse(r.text)}
    assert slugs == {"banana-1kg", "apple-1kg"}


async def test_export_filters_by_subcategory(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    await upload_and_apply(
        client,
        admin_auth_headers,
        [
            row(),
            row(
                subcategory_slug="dried-fruits",
                subcategory_name="Dried Fruits",
                product_slug="raisins-500g",
                product_name="Raisins 500g",
            ),
        ],
    )
    from app.models.catalog import Subcategory

    dried = (
        await session.exec(
            select(Subcategory).where(Subcategory.slug == "dried-fruits")
        )
    ).first()
    assert dried is not None
    r = await client.get(
        f"{EXPORT}?subcategory_id={dried.id}", headers=admin_auth_headers
    )
    assert {rec["product_slug"] for rec in parse(r.text)} == {"raisins-500g"}


async def test_export_excludes_soft_deleted_unless_asked(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    await upload_and_apply(
        client, admin_auth_headers, [row(product_slug="a"), row(product_slug="b")]
    )
    gone = (
        await session.exec(select(MasterProduct).where(MasterProduct.slug == "a"))
    ).first()
    assert gone is not None
    await client.delete(
        f"/api/v1/catalog/admin/products/{gone.id}", headers=admin_auth_headers
    )

    default = await client.get(EXPORT, headers=admin_auth_headers)
    assert {r["product_slug"] for r in parse(default.text)} == {"b"}

    inclusive = await client.get(
        f"{EXPORT}?include_inactive=true", headers=admin_auth_headers
    )
    assert {r["product_slug"] for r in parse(inclusive.text)} == {"a", "b"}


async def test_reimporting_an_inactive_export_reactivates(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """The documented way to undo a bulk deactivation."""
    await upload_and_apply(client, admin_auth_headers, [row()])
    product = (
        await session.exec(
            select(MasterProduct).where(MasterProduct.slug == "banana-1kg")
        )
    ).first()
    assert product is not None
    await client.delete(
        f"/api/v1/catalog/admin/products/{product.id}", headers=admin_auth_headers
    )

    exported = (
        await client.get(f"{EXPORT}?include_inactive=true", headers=admin_auth_headers)
    ).text
    job = await upload_and_apply_raw(client, admin_auth_headers, exported)
    assert job["status"] == "applied"
    await session.refresh(product)
    assert product.is_active is True


async def upload_and_apply_raw(
    client: AsyncClient, headers: dict[str, str], text: str
) -> dict[str, object]:
    created = await upload(client, headers, [], raw=text.encode("utf-8"))
    assert created.status_code == 200, created.text
    applied = await client.post(
        f"{IMPORTS}/{created.json()['id']}/apply", headers=headers
    )
    assert applied.status_code == 200, applied.text
    return dict(applied.json())
