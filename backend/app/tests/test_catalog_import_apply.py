# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Phase 2 of the bulk import: apply writes the staged rows.

Celery runs eager in tests, so `POST /apply` executes the task inline and the
response already reflects the finished job.
"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import (
    Category,
    MasterProduct,
    MasterProductImage,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from tests.catalog_csv_fixtures import (
    IMPORTS,
    counts,
    row,
    upload,
    upload_and_apply,
)

pytestmark = pytest.mark.asyncio


async def _product(session: AsyncSession, slug: str) -> MasterProduct:
    found = (
        await session.exec(select(MasterProduct).where(MasterProduct.slug == slug))
    ).first()
    assert found is not None, f"product {slug} was not created"
    return found


async def _en_name(session: AsyncSession, product_id: int) -> str:
    trans = (
        await session.exec(
            select(MasterProductTranslation)
            .where(MasterProductTranslation.master_product_id == product_id)
            .where(MasterProductTranslation.language_code == "en")
        )
    ).first()
    assert trans is not None
    return trans.name


async def test_apply_creates_the_whole_hierarchy(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    job = await upload_and_apply(
        client,
        admin_auth_headers,
        [
            row(
                product_slug="banana-1kg",
                product_description="Fresh robusta",
                brand="Local Farm",
                unit="kg",
                service_sort_order="3",
            ),
            row(product_slug="apple-1kg", base_price="200"),
        ],
    )
    assert job["status"] == "applied", job
    assert job["applied_at"] is not None
    assert job["failure_reason"] is None
    assert counts(job["applied"], "service")["create"] == 1
    assert counts(job["applied"], "product")["create"] == 2

    service = (
        await session.exec(select(Service).where(Service.slug == "grocery"))
    ).first()
    assert service is not None and service.is_active and service.sort_order == 3
    svc_t = (
        await session.exec(
            select(ServiceTranslation).where(
                ServiceTranslation.service_id == service.id
            )
        )
    ).first()
    assert svc_t is not None and svc_t.name == "Grocery"

    category = (
        await session.exec(select(Category).where(Category.slug == "fruits"))
    ).first()
    assert category is not None and category.service_id == service.id

    sub = (
        await session.exec(
            select(Subcategory).where(Subcategory.slug == "fresh-fruits")
        )
    ).first()
    assert sub is not None and sub.category_id == category.id
    sub_t = (
        await session.exec(
            select(SubcategoryTranslation).where(
                SubcategoryTranslation.subcategory_id == sub.id
            )
        )
    ).first()
    assert sub_t is not None and sub_t.name == "Fresh Fruits"

    banana = await _product(session, "banana-1kg")
    assert banana.subcategory_id == sub.id
    assert banana.base_price == pytest.approx(60.0)
    assert banana.brand == "Local Farm"
    assert banana.unit == "kg"
    assert await _en_name(session, banana.id or 0) == "Banana 1kg"

    apple = await _product(session, "apple-1kg")
    assert apple.base_price == pytest.approx(200.0)


async def test_parents_are_created_once_across_many_rows(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    await upload_and_apply(
        client,
        admin_auth_headers,
        [row(product_slug=f"p-{i}") for i in range(5)],
    )
    services = (await session.exec(select(Service))).all()
    categories = (await session.exec(select(Category))).all()
    subs = (await session.exec(select(Subcategory))).all()
    assert len(services) == 1
    assert len(categories) == 1
    assert len(subs) == 1
    assert len((await session.exec(select(MasterProduct))).all()) == 5


async def test_apply_is_idempotent_second_file_is_all_noop(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    rows = [row(product_slug="banana-1kg"), row(product_slug="apple-1kg")]
    await upload_and_apply(client, admin_auth_headers, rows)
    second = await upload_and_apply(client, admin_auth_headers, rows)

    assert second["status"] == "applied"
    for level in ("service", "category", "subcategory", "product"):
        assert counts(second["applied"], level)["create"] == 0, level
        assert counts(second["applied"], level)["update"] == 0, level
    assert len((await session.exec(select(MasterProduct))).all()) == 2


async def test_update_changes_price_name_and_brand(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    await upload_and_apply(client, admin_auth_headers, [row()])
    job = await upload_and_apply(
        client,
        admin_auth_headers,
        [row(product_name="Banana Robusta 1kg", base_price="72.50", brand="Farm Co")],
    )
    assert counts(job["applied"], "product")["update"] == 1

    product = await _product(session, "banana-1kg")
    await session.refresh(product)
    assert product.base_price == pytest.approx(72.50)
    assert product.brand == "Farm Co"
    assert await _en_name(session, product.id or 0) == "Banana Robusta 1kg"


async def test_rename_keeps_the_same_product_row(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """Slug is identity, so "same slug, new name" must not fork a duplicate."""
    await upload_and_apply(client, admin_auth_headers, [row()])
    original = await _product(session, "banana-1kg")
    original_id = original.id

    await upload_and_apply(
        client, admin_auth_headers, [row(product_name="Bananas, Robusta")]
    )
    products = (await session.exec(select(MasterProduct))).all()
    assert len(products) == 1
    assert products[0].id == original_id


async def test_apply_reactivates_a_soft_deleted_product(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    await upload_and_apply(client, admin_auth_headers, [row()])
    product = await _product(session, "banana-1kg")
    product_id = product.id

    deleted = await client.delete(
        f"/api/v1/catalog/admin/products/{product_id}", headers=admin_auth_headers
    )
    assert deleted.status_code == 200

    planned = await upload(client, admin_auth_headers, [row()])
    assert counts(planned.json()["plan"], "product")["update"] == 1
    applied = await client.post(
        f"{IMPORTS}/{planned.json()['id']}/apply", headers=admin_auth_headers
    )
    assert applied.status_code == 200

    # Reactivated in place, not forked into a second row.
    products = (await session.exec(select(MasterProduct))).all()
    assert len(products) == 1
    await session.refresh(products[0])
    assert products[0].id == product_id
    assert products[0].is_active is True


async def test_apply_reactivates_a_soft_deleted_service(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """`Service.slug` is globally unique, so forking here would be impossible
    anyway — re-import has to reactivate."""
    await upload_and_apply(client, admin_auth_headers, [row()])
    service = (
        await session.exec(select(Service).where(Service.slug == "grocery"))
    ).first()
    assert service is not None
    await client.delete(
        f"/api/v1/catalog/admin/services/{service.id}", headers=admin_auth_headers
    )

    job = await upload_and_apply(client, admin_auth_headers, [row()])
    assert job["status"] == "applied", job
    assert counts(job["applied"], "service")["update"] == 1
    services = (await session.exec(select(Service))).all()
    assert len(services) == 1
    await session.refresh(services[0])
    assert services[0].is_active is True


async def test_non_english_translations_are_written(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    await upload_and_apply(
        client,
        admin_auth_headers,
        [
            row(
                product_name_hi="केला 1 किग्रा",
                product_desc_hi="ताज़े केले",
                product_name_mr="केळी 1 किलो",
            )
        ],
    )
    product = await _product(session, "banana-1kg")
    trans = (
        await session.exec(
            select(MasterProductTranslation).where(
                MasterProductTranslation.master_product_id == product.id
            )
        )
    ).all()
    by_lang = {t.language_code: t for t in trans}
    assert by_lang["hi"].name == "केला 1 किग्रा"
    assert by_lang["hi"].description == "ताज़े केले"
    assert by_lang["mr"].name == "केळी 1 किलो"
    # NOT NULL column, so a name-only language still needs a description value.
    assert by_lang["mr"].description == ""
    assert "gu" not in by_lang


async def test_create_seeds_image_row_zero_from_the_csv_url(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """Mirrors `create_product_admin`: the collection and image_url must agree
    from the start, or the first image added later silently replaces the cover.
    """
    url = "https://example.com/banana.jpg"
    await upload_and_apply(client, admin_auth_headers, [row(product_image_url=url)])
    product = await _product(session, "banana-1kg")
    assert product.image_url == url
    images = (
        await session.exec(
            select(MasterProductImage).where(
                MasterProductImage.master_product_id == product.id
            )
        )
    ).all()
    assert len(images) == 1
    assert images[0].position == 0
    assert images[0].url == url
    assert images[0].source == "external"


async def test_import_does_not_clobber_a_curated_image_collection(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """`PUT /products/{id}` refuses to write image_url because the collection
    owns the cover; import honours the same invariant on update."""
    first = "https://example.com/first.jpg"
    await upload_and_apply(client, admin_auth_headers, [row(product_image_url=first)])
    product = await _product(session, "banana-1kg")

    job = await upload_and_apply(
        client,
        admin_auth_headers,
        [row(product_image_url="https://example.com/second.jpg")],
    )
    # Already has an image, so the new URL is ignored entirely — including in
    # the diff, which must still read as noop.
    assert counts(job["applied"], "product")["noop"] == 1
    await session.refresh(product)
    assert product.image_url == first
    images = (
        await session.exec(
            select(MasterProductImage).where(
                MasterProductImage.master_product_id == product.id
            )
        )
    ).all()
    assert len(images) == 1


async def test_error_rows_are_skipped_by_apply(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    job = await upload_and_apply(
        client,
        admin_auth_headers,
        [
            row(product_slug="good-1"),
            row(product_slug="bad-1", base_price="oops"),
            row(product_slug="good-2"),
        ],
    )
    assert job["status"] == "applied"
    assert counts(job["applied"], "product")["create"] == 2
    slugs = {p.slug for p in (await session.exec(select(MasterProduct))).all()}
    assert slugs == {"good-1", "good-2"}


async def test_apply_stamps_every_processed_row(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    created = await upload(
        client,
        admin_auth_headers,
        [row(product_slug="a"), row(product_slug="b", base_price="x")],
    )
    job_id = created.json()["id"]
    await client.post(f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers)

    rows = (
        await client.get(f"{IMPORTS}/{job_id}/rows", headers=admin_auth_headers)
    ).json()["items"]
    by_line = {r["line_number"]: r for r in rows}
    assert by_line[1]["applied_at"] is not None
    assert by_line[1]["apply_error"] is None
    # The error row is never processed, so it stays unstamped.
    assert by_line[2]["applied_at"] is None


async def test_reapply_of_an_applied_job_is_rejected(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    created = await upload(client, admin_auth_headers, [row()])
    job_id = created.json()["id"]
    assert (
        await client.post(f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers)
    ).status_code == 200
    again = await client.post(f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers)
    assert again.status_code == 409
    assert again.json()["detail"] == "import_not_appliable"


async def test_apply_rejected_when_no_row_is_valid(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    created = await upload(
        client, admin_auth_headers, [row(base_price="nope")]
    )
    job_id = created.json()["id"]
    r = await client.post(f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers)
    assert r.status_code == 409
    assert r.json()["detail"] == "import_has_no_valid_rows"


async def test_cancel_blocks_apply_and_keeps_the_rows(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    created = await upload(client, admin_auth_headers, [row()])
    job_id = created.json()["id"]

    cancelled = await client.delete(f"{IMPORTS}/{job_id}", headers=admin_auth_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    blocked = await client.post(f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers)
    assert blocked.status_code == 409

    rows = await client.get(f"{IMPORTS}/{job_id}/rows", headers=admin_auth_headers)
    assert rows.json()["total"] == 1


async def test_cancel_after_apply_is_rejected(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    created = await upload(client, admin_auth_headers, [row()])
    job_id = created.json()["id"]
    await client.post(f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers)
    r = await client.delete(f"{IMPORTS}/{job_id}", headers=admin_auth_headers)
    assert r.status_code == 409
    assert r.json()["detail"] == "import_not_cancellable"


async def test_multi_service_file_creates_each_branch(
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
        ],
    )
    assert len((await session.exec(select(Service))).all()) == 2
    assert len((await session.exec(select(Category))).all()) == 2
    assert len((await session.exec(select(Subcategory))).all()) == 2
    assert len((await session.exec(select(MasterProduct))).all()) == 2


async def test_same_product_slug_under_two_subcategories_creates_two_rows(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """Product uniqueness is per-subcategory, so this is not a duplicate."""
    await upload_and_apply(
        client,
        admin_auth_headers,
        [
            row(),
            row(subcategory_slug="dried-fruits", subcategory_name="Dried Fruits"),
        ],
    )
    products = (
        await session.exec(
            select(MasterProduct).where(MasterProduct.slug == "banana-1kg")
        )
    ).all()
    assert len(products) == 2
    assert len({p.subcategory_id for p in products}) == 2


async def test_chunked_apply_handles_more_rows_than_one_chunk(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """APPLY_CHUNK is 200; 250 rows exercises the second chunk and the parent
    cache surviving across chunk commits."""
    rows = [row(product_slug=f"p-{i:04d}") for i in range(250)]
    job = await upload_and_apply(client, admin_auth_headers, rows)
    assert job["status"] == "applied", job
    assert counts(job["applied"], "product")["create"] == 250
    assert counts(job["applied"], "service")["create"] == 1
    assert len((await session.exec(select(Service))).all()) == 1
    assert (
        len(
            (
                await session.exec(
                    select(MasterProduct).where(col(MasterProduct.is_active).is_(True))
                )
            ).all()
        )
        == 250
    )


async def test_apply_claims_the_job_before_enqueueing(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """The status flip must happen in the REQUEST, not inside the task.

    Found by a live run against a stack with no Celery worker: the task sat in
    Redis, the job still read `validated`, and the UI showed no sign the click
    had done anything — so every further click enqueued another task. With the
    request claiming the job, the response says `applying` and a second click
    is a 409.
    """
    created = await upload(client, admin_auth_headers, [row()])
    job_id = created.json()["id"]

    # Simulate a worker that never picks the task up.
    with patch("app.worker.apply_catalog_import.delay") as delay:
        first = await client.post(
            f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers
        )
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "applying"
        assert delay.call_count == 1

        second = await client.post(
            f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers
        )
        assert second.status_code == 409
        assert second.json()["detail"] == "import_not_appliable"
        # The double click must NOT have queued a second task.
        assert delay.call_count == 1

    from app.models.catalog_import import CatalogImportJob

    persisted = await session.get(CatalogImportJob, job_id)
    assert persisted is not None
    await session.refresh(persisted)
    assert persisted.status.value == "applying"


async def test_a_claimed_job_still_applies_when_the_worker_runs(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """`apply_job` must accept the `applying` row the endpoint handed it."""
    from app.services.catalog_import import apply_job

    created = await upload(client, admin_auth_headers, [row()])
    job_id = created.json()["id"]
    with patch("app.worker.apply_catalog_import.delay"):
        await client.post(f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers)

    job = await apply_job(session, job_id)
    assert job.status.value == "applied"
    assert (await _product(session, "banana-1kg")) is not None


async def test_one_row_failing_at_apply_time_does_not_poison_the_chunk(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """The per-row savepoint branch: an unexpected failure on one row is
    recorded against that row and the rest of the chunk still lands.

    Forced by patching `apply_product`, because validation already rejects
    everything reachable from the CSV — the real trigger would be a slug that
    raced into existence between validate and apply.
    """
    from app.services import catalog_import as svc

    created = await upload(
        client,
        admin_auth_headers,
        [row(product_slug="ok-1"), row(product_slug="boom"), row(product_slug="ok-2")],
    )
    job_id = created.json()["id"]

    real_apply = svc._Applier.apply_product

    async def flaky(self: object, staged: object) -> None:
        if staged.data.get("product_slug") == "boom":  # type: ignore[attr-defined]
            raise RuntimeError("simulated slug collision")
        await real_apply(self, staged)  # type: ignore[arg-type]

    with patch.object(svc._Applier, "apply_product", flaky):
        applied = await client.post(
            f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers
        )
    assert applied.status_code == 200, applied.text
    body = applied.json()

    # The job reports failure honestly rather than claiming success.
    assert body["status"] == "failed"
    assert "1 row(s) failed to apply" in (body["failure_reason"] or "")

    # The two good rows still landed.
    slugs = {p.slug for p in (await session.exec(select(MasterProduct))).all()}
    assert slugs == {"ok-1", "ok-2"}

    rows = (
        await client.get(f"{IMPORTS}/{job_id}/rows", headers=admin_auth_headers)
    ).json()["items"]
    by_slug = {r["data"]["product_slug"]: r for r in rows}
    # Failure recorded on the row, and stamped so a resume does not loop on it.
    assert by_slug["boom"]["apply_error"] == "simulated slug collision"
    assert by_slug["boom"]["applied_at"] is not None
    assert by_slug["ok-1"]["apply_error"] is None
    assert by_slug["ok-2"]["apply_error"] is None


async def test_a_failed_job_can_be_resumed_without_double_writing(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """Resume from `failed` skips rows already stamped `applied_at`."""
    from app.services import catalog_import as svc

    created = await upload(
        client,
        admin_auth_headers,
        [row(product_slug="ok-1"), row(product_slug="boom")],
    )
    job_id = created.json()["id"]
    real_apply = svc._Applier.apply_product

    async def flaky(self: object, staged: object) -> None:
        if staged.data.get("product_slug") == "boom":  # type: ignore[attr-defined]
            raise RuntimeError("transient")
        await real_apply(self, staged)  # type: ignore[arg-type]

    with patch.object(svc._Applier, "apply_product", flaky):
        assert (
            await client.post(f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers)
        ).json()["status"] == "failed"

    # Re-apply with the fault gone: every row is already stamped, so nothing is
    # rewritten and no duplicate product appears.
    resumed = await client.post(f"{IMPORTS}/{job_id}/apply", headers=admin_auth_headers)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "applied"
    products = (await session.exec(select(MasterProduct))).all()
    assert {p.slug for p in products} == {"ok-1"}
    assert len(products) == 1
