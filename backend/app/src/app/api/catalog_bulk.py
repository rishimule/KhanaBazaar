# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin bulk catalog operations: CSV import/export and multi-select activation.

Split out of `api/catalog_admin.py` (already 1,200+ lines of per-row CRUD) so
the bulk write path has its own file. Mounted under the same `/catalog` prefix,
so every route here lives at `/api/v1/catalog/admin/...`.

The import is two-phase by design:

1. ``POST /imports`` parses, validates and stages every row **without writing
   to the catalog**, returning the plan. Validation runs inline — it is bounded
   by the 5,000-row cap in `services/catalog_csv.py` and amounts to four bulk
   SELECTs plus a Python pass, so the operator gets an immediate preview with no
   polling.
2. ``POST /imports/{id}/apply`` hands the staged rows to Celery. That is the
   phase that writes thousands of rows and fans out the per-product search
   reindex, so it stays off the request path.

``GET /export.csv`` emits the exact same column set the importer accepts, which
is what makes bulk *editing* possible: export, edit in a spreadsheet, re-import.
An unedited export re-imports as all-noop, and `tests/test_catalog_export.py`
holds that invariant.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.base import User
from app.models.catalog import Category, MasterProduct, Service, Subcategory
from app.models.catalog_import import (
    CatalogImportJob,
    CatalogImportRow,
    CatalogImportRowAction,
    CatalogImportStatus,
)
from app.schemas.catalog_import import (
    BulkStatusRequest,
    BulkStatusResponse,
    ImportJobRead,
    ImportRowRead,
)
from app.schemas.pagination import PagedResponse
from app.services.catalog_csv import CatalogCsvError, template_csv
from app.services.catalog_import import (
    APPLIABLE_STATUSES,
    export_catalog_rows,
    plan_and_stage,
    rows_to_csv,
)

router = APIRouter(prefix="/admin", tags=["catalog-admin"])

# Matches the per-row-audit cap admins get on inventory bulk edits
# (`_ADMIN_BULK_ROW_LIMIT` in api/stores.py) — a selection this large is a sign
# the operator wants the CSV path, not a grid selection.
_BULK_STATUS_LIMIT = 500

# Typed as `type[Any]`: the four models share `id`/`is_active` but no common
# base narrow enough for mypy to see them through a dict lookup.
_ENTITY_MODELS: Dict[str, Any] = {
    "service": Service,
    "category": Category,
    "subcategory": Subcategory,
    "product": MasterProduct,
}


def _job_read(job: CatalogImportJob) -> ImportJobRead:
    assert job.id is not None
    return ImportJobRead(
        id=job.id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        filename=job.filename,
        status=job.status.value,
        created_by_admin_id=job.created_by_admin_id,
        total_rows=job.total_rows,
        error_rows=job.error_rows,
        plan=job.plan or {},
        applied=job.applied or None,
        failure_reason=job.failure_reason,
        applied_at=job.applied_at,
    )


def _row_read(row: CatalogImportRow) -> ImportRowRead:
    assert row.id is not None
    return ImportRowRead(
        id=row.id,
        line_number=row.line_number,
        action=row.action.value,
        data=row.data or {},
        errors=row.errors or [],
        level_plan=row.level_plan or {},
        applied_at=row.applied_at,
        apply_error=row.apply_error,
    )


async def _get_job(session: AsyncSession, job_id: int) -> CatalogImportJob:
    job = await session.get(CatalogImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="import_not_found")
    return job


# ─── Template + export (static paths declared before /{job_id}) ──


@router.get("/imports/template.csv")
async def download_import_template(
    admin: User = Depends(get_current_admin),
) -> Response:
    """Blank template: the full header plus one illustrative row."""
    return Response(
        content=template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="catalog-import-template.csv"'
        },
    )


@router.get("/export.csv")
async def export_catalog(
    service_id: Optional[int] = Query(default=None),
    category_id: Optional[int] = Query(default=None),
    subcategory_id: Optional[int] = Query(default=None),
    include_inactive: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> Response:
    """Export products in the importer's column shape.

    Filters mirror the admin table's drill-down so an operator can export just
    the subtree they are looking at. `include_inactive` pulls in soft-deleted
    rows — re-importing those *reactivates* them, which is the intended way to
    undo a bulk deactivation.
    """
    records = await export_catalog_rows(
        session,
        service_id=service_id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        include_inactive=include_inactive,
    )
    return Response(
        content=rows_to_csv(records),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="catalog-export.csv"'},
    )


# ─── Import: upload (phase 1) ──────────────────────────────────


@router.post("/imports", response_model=ImportJobRead)
async def upload_catalog_import(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ImportJobRead:
    """Parse, validate and stage a CSV. Writes nothing to the catalog."""
    assert admin.id is not None
    raw = await file.read()
    try:
        job = await plan_and_stage(
            session,
            filename=file.filename or "upload.csv",
            raw=raw,
            admin_id=admin.id,
        )
    except CatalogCsvError as exc:
        await session.rollback()
        status_code = 413 if exc.code == "file_too_large" else 422
        raise HTTPException(status_code=status_code, detail=exc.to_detail()) from exc
    response = _job_read(job)
    await session.commit()
    return response


@router.get("/imports", response_model=PagedResponse[ImportJobRead])
async def list_catalog_imports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> PagedResponse[ImportJobRead]:
    total = (
        await session.exec(select(func.count()).select_from(CatalogImportJob))
    ).one()
    rows = (
        await session.exec(
            select(CatalogImportJob)
            .order_by(col(CatalogImportJob.id).desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return PagedResponse[ImportJobRead](
        items=[_job_read(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


@router.get("/imports/{job_id}", response_model=ImportJobRead)
async def get_catalog_import(
    job_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ImportJobRead:
    return _job_read(await _get_job(session, job_id))


@router.get("/imports/{job_id}/rows", response_model=PagedResponse[ImportRowRead])
async def list_catalog_import_rows(
    job_id: int,
    only_errors: bool = Query(default=False),
    action: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> PagedResponse[ImportRowRead]:
    """Paginated staged rows.

    Server-side pagination is the point of staging: a 3,000-row error report
    would otherwise have to be shipped to the browser in one response.
    """
    await _get_job(session, job_id)

    filters: List[Any] = [CatalogImportRow.job_id == job_id]
    if only_errors:
        filters.append(col(CatalogImportRow.action) == CatalogImportRowAction.Error)
    elif action is not None:
        try:
            wanted = CatalogImportRowAction(action)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="unknown_action") from exc
        filters.append(col(CatalogImportRow.action) == wanted)

    count_stmt = select(func.count()).select_from(CatalogImportRow)
    for clause in filters:
        count_stmt = count_stmt.where(clause)
    total = (await session.exec(count_stmt)).one()

    stmt = select(CatalogImportRow)
    for clause in filters:
        stmt = stmt.where(clause)
    rows = (
        await session.exec(
            stmt.order_by(col(CatalogImportRow.line_number))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return PagedResponse[ImportRowRead](
        items=[_row_read(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


# ─── Import: apply (phase 2) + cancel ──────────────────────────


@router.post("/imports/{job_id}/apply", response_model=ImportJobRead)
async def apply_catalog_import_endpoint(
    job_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ImportJobRead:
    """Claim the job and hand its staged rows to the worker.

    Re-appliable from `failed`: rows already stamped `applied_at` are skipped,
    so a job that died mid-run resumes rather than double-writing.

    The status is flipped to `applying` **here**, before enqueueing, not inside
    the task. Doing it on the worker meant a broker or worker outage left the
    job reading `validated` with no sign the click had done anything, and every
    further click enqueued another task. Claiming it in the request makes the UI
    show `applying` immediately and turns a double-click into a 409.
    """
    job = await _get_job(session, job_id)
    if job.status not in APPLIABLE_STATUSES:
        raise HTTPException(status_code=409, detail="import_not_appliable")
    if job.total_rows == job.error_rows:
        raise HTTPException(status_code=409, detail="import_has_no_valid_rows")

    job.status = CatalogImportStatus.Applying
    job.failure_reason = None
    session.add(job)
    # Commit before the task opens its own session: under eager Celery (tests)
    # it runs inline and would otherwise contend with the row held here.
    await session.commit()

    from app.worker import apply_catalog_import

    apply_catalog_import.delay(job_id)

    refreshed = await _get_job(session, job_id)
    await session.refresh(refreshed)
    return _job_read(refreshed)


@router.delete("/imports/{job_id}", response_model=ImportJobRead)
async def cancel_catalog_import(
    job_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> ImportJobRead:
    """Discard a validated import. Staged rows are kept as the record of it."""
    job = await _get_job(session, job_id)
    if job.status != CatalogImportStatus.Validated:
        raise HTTPException(status_code=409, detail="import_not_cancellable")
    job.status = CatalogImportStatus.Cancelled
    session.add(job)
    await session.flush()
    response = _job_read(job)
    await session.commit()
    return response


# ─── Multi-select activation ───────────────────────────────────


@router.post("/bulk/status", response_model=BulkStatusResponse)
async def bulk_set_active(
    payload: BulkStatusRequest,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_current_admin),
) -> BulkStatusResponse:
    """Activate or deactivate a selection from the admin catalog table.

    Soft only — `is_active` is the same flag the per-row Deactivate button
    writes, and like that button it does **not** cascade to children (the UI
    warns with the child count instead). Ids that were already in the requested
    state come back in `unchanged` so the UI can explain a partial count.
    """
    ids = list(dict.fromkeys(payload.ids))  # dedupe, preserve order
    if not ids:
        raise HTTPException(status_code=422, detail="ids_required")
    if len(ids) > _BULK_STATUS_LIMIT:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ROW_LIMIT",
                "message": f"At most {_BULK_STATUS_LIMIT} items per request",
            },
        )

    model = _ENTITY_MODELS[payload.entity]
    rows = (await session.exec(select(model).where(col(model.id).in_(ids)))).all()
    found = {r.id: r for r in rows}

    updated = 0
    unchanged: List[int] = []
    for entity_id in ids:
        row = found.get(entity_id)
        if row is None:
            continue
        if row.is_active == payload.is_active:
            unchanged.append(entity_id)
            continue
        row.is_active = payload.is_active
        session.add(row)
        updated += 1

    await session.commit()
    return BulkStatusResponse(
        updated=updated,
        unchanged=unchanged,
        not_found=[i for i in ids if i not in found],
    )
