// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { ApiError, del, get, post } from "@/lib/api";
import type {
  BulkStatusResult,
  EntityKind,
  ImportFileError,
  ImportJob,
  ImportRow,
  PagedResponse,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ROOT = "/api/v1/catalog/admin";

export interface ExportFilters {
  serviceId?: number;
  categoryId?: number;
  subcategoryId?: number;
  includeInactive?: boolean;
}

function exportQuery(filters: ExportFilters): string {
  const p = new URLSearchParams();
  if (filters.serviceId) p.set("service_id", String(filters.serviceId));
  if (filters.categoryId) p.set("category_id", String(filters.categoryId));
  if (filters.subcategoryId) p.set("subcategory_id", String(filters.subcategoryId));
  if (filters.includeInactive) p.set("include_inactive", "true");
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}

/** Multipart upload — uses fetch directly so the browser sets the multipart
 *  boundary (the shared `post` helper forces application/json).
 *
 *  A 4xx here is a FILE-level rejection with a `{code, message, columns?}`
 *  detail and nothing staged; row-level problems come back as a 200 with
 *  `error_rows > 0`. */
export async function uploadCatalogCsv(
  file: File,
  token: string | null,
): Promise<ImportJob> {
  const form = new FormData();
  form.append("file", file, file.name);
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${ROOT}/imports`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    // Pass the detail through untouched — it carries `columns` for the
    // missing/unknown-column cases. Read it with `importFileError()` below,
    // never by rendering `err.detail` directly.
    throw new ApiError(body.detail ?? "upload_failed", res.status);
  }
  return res.json() as Promise<ImportJob>;
}

export function listImportJobs(
  token: string | null,
  page = 1,
  pageSize = 20,
): Promise<PagedResponse<ImportJob>> {
  return get<PagedResponse<ImportJob>>(
    `${ROOT}/imports?page=${page}&page_size=${pageSize}`,
    token,
  );
}

export function getImportJob(
  jobId: number,
  token: string | null,
): Promise<ImportJob> {
  return get<ImportJob>(`${ROOT}/imports/${jobId}`, token);
}

export function listImportRows(
  jobId: number,
  token: string | null,
  opts: { onlyErrors?: boolean; page?: number; pageSize?: number } = {},
): Promise<PagedResponse<ImportRow>> {
  const p = new URLSearchParams();
  if (opts.onlyErrors) p.set("only_errors", "true");
  p.set("page", String(opts.page ?? 1));
  p.set("page_size", String(opts.pageSize ?? 50));
  return get<PagedResponse<ImportRow>>(
    `${ROOT}/imports/${jobId}/rows?${p.toString()}`,
    token,
  );
}

export function applyImportJob(
  jobId: number,
  token: string | null,
): Promise<ImportJob> {
  return post<ImportJob>(`${ROOT}/imports/${jobId}/apply`, undefined, token);
}

export function cancelImportJob(
  jobId: number,
  token: string | null,
): Promise<ImportJob> {
  return del<ImportJob>(`${ROOT}/imports/${jobId}`, token);
}

/** Trigger a browser download for a CSV endpoint.
 *
 *  Fetched with the auth header rather than opened as a link, because these
 *  routes are admin-only and a bare `window.open` sends no Authorization. */
async function downloadCsv(
  path: string,
  filename: string,
  token: string | null,
): Promise<void> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (!res.ok) throw new ApiError("download_failed", res.status);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function downloadImportTemplate(token: string | null): Promise<void> {
  return downloadCsv(
    `${ROOT}/imports/template.csv`,
    "catalog-import-template.csv",
    token,
  );
}

export function downloadCatalogExport(
  filters: ExportFilters,
  token: string | null,
): Promise<void> {
  return downloadCsv(
    `${ROOT}/export.csv${exportQuery(filters)}`,
    "catalog-export.csv",
    token,
  );
}

export function bulkSetActive(
  entity: EntityKind,
  ids: number[],
  isActive: boolean,
  token: string | null,
): Promise<BulkStatusResult> {
  return post<BulkStatusResult>(
    `${ROOT}/bulk/status`,
    { entity, ids, is_active: isActive },
    token,
  );
}

/** Narrow a caught upload error to the backend's file-level detail shape.
 *
 *  `apiErrorCode()` from `@/lib/errors` gets the code, but the column list on
 *  `missing_columns` / `unknown_columns` is the whole value of the message, so
 *  this reads the object safely instead. */
export function importFileError(err: unknown): ImportFileError | null {
  if (!(err instanceof ApiError)) return null;
  const detail = err.detail;
  if (typeof detail === "string") return { code: detail, message: detail };
  if (detail && typeof detail === "object") {
    const bag = detail as Record<string, unknown>;
    const code = typeof bag.code === "string" ? bag.code : null;
    if (!code) return null;
    return {
      code,
      message: typeof bag.message === "string" ? bag.message : code,
      columns: Array.isArray(bag.columns)
        ? bag.columns.filter((c): c is string => typeof c === "string")
        : undefined,
    };
  }
  return null;
}
