"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

// English-only by design, following the `Wallet credit` operator-tool
// precedent in `admin/layout.tsx`: the CSV column names this page has to name
// (`service_slug`, `base_price`, …) are English regardless of dashboard locale,
// so a half-translated page would read worse than an English one.

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import {
  applyImportJob,
  cancelImportJob,
  downloadCatalogExport,
  downloadImportTemplate,
  getImportJob,
  importFileError,
  listImportJobs,
  listImportRows,
  uploadCatalogCsv,
} from "@/lib/catalogImport";
import type {
  EntityKind,
  ImportFileError,
  ImportJob,
  ImportPlan,
  ImportRow,
} from "@/types";
import styles from "./import.module.css";

const LEVELS: EntityKind[] = ["service", "category", "subcategory", "product"];
const ROWS_PER_PAGE = 25;
/** Statuses that are still moving, so the job row needs re-fetching. */
const POLLED_STATUSES = new Set(["applying"]);

function planTotal(plan: ImportPlan, key: "create" | "update" | "noop"): number {
  return LEVELS.reduce((sum, level) => sum + (plan[level]?.[key] ?? 0), 0);
}

function fileErrorText(err: ImportFileError): string {
  if (err.columns?.length) {
    return `${err.message}: ${err.columns.join(", ")}`;
  }
  return err.message;
}

export default function AdminCatalogImportPage() {
  const { token, dbUser, loading: authLoading } = useAuth();

  const [job, setJob] = useState<ImportJob | null>(null);
  const [rows, setRows] = useState<ImportRow[]>([]);
  const [rowTotal, setRowTotal] = useState(0);
  const [rowPage, setRowPage] = useState(1);
  const [onlyErrors, setOnlyErrors] = useState(false);
  const [history, setHistory] = useState<ImportJob[]>([]);

  const [busy, setBusy] = useState<"upload" | "apply" | "cancel" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refreshHistory = useCallback(async () => {
    try {
      const page = await listImportJobs(token, 1, 10);
      setHistory(page.items);
    } catch {
      /* history is informational — never block the main flow on it */
    }
  }, [token]);

  useEffect(() => {
    if (token) void refreshHistory();
  }, [token, refreshHistory]);

  const loadRows = useCallback(
    async (jobId: number, page: number, errorsOnly: boolean) => {
      const result = await listImportRows(jobId, token, {
        onlyErrors: errorsOnly,
        page,
        pageSize: ROWS_PER_PAGE,
      });
      setRows(result.items);
      setRowTotal(result.total);
    },
    [token],
  );

  useEffect(() => {
    if (!job) return;
    void loadRows(job.id, rowPage, onlyErrors);
  }, [job, rowPage, onlyErrors, loadRows]);

  // The apply task runs on the worker, so an `applying` job needs polling.
  // Eager Celery in dev/test usually finishes before the first tick.
  useEffect(() => {
    if (!job || !POLLED_STATUSES.has(job.status)) return;
    const timer = setInterval(async () => {
      try {
        const fresh = await getImportJob(job.id, token);
        setJob(fresh);
        if (!POLLED_STATUSES.has(fresh.status)) void refreshHistory();
      } catch {
        /* transient — the next tick retries */
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [job, token, refreshHistory]);

  async function onUpload(file: File) {
    setBusy("upload");
    setError(null);
    try {
      const created = await uploadCatalogCsv(file, token);
      setJob(created);
      setRowPage(1);
      setOnlyErrors(created.error_rows > 0);
      void refreshHistory();
    } catch (err) {
      const parsed = importFileError(err);
      setError(
        parsed
          ? fileErrorText(parsed)
          : "Upload failed. Check the file and try again.",
      );
      setJob(null);
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function onApply() {
    if (!job) return;
    setBusy("apply");
    setError(null);
    try {
      setJob(await applyImportJob(job.id, token));
      void refreshHistory();
    } catch {
      setError("Could not start the import. Reload and check its status.");
    } finally {
      setBusy(null);
    }
  }

  async function onCancel() {
    if (!job) return;
    setBusy("cancel");
    setError(null);
    try {
      setJob(await cancelImportJob(job.id, token));
      void refreshHistory();
    } catch {
      setError("Could not discard this import.");
    } finally {
      setBusy(null);
    }
  }

  async function onDownload(kind: "template" | "export") {
    setError(null);
    try {
      if (kind === "template") await downloadImportTemplate(token);
      else await downloadCatalogExport({}, token);
    } catch {
      setError("Download failed.");
    }
  }

  if (authLoading) return <p className={styles.muted}>Loading…</p>;
  if (!dbUser || dbUser.role !== "admin") {
    return <p className={styles.muted}>Admins only.</p>;
  }

  const canApply =
    job !== null &&
    (job.status === "validated" || job.status === "failed") &&
    job.total_rows > job.error_rows;
  const totalPages = Math.max(1, Math.ceil(rowTotal / ROWS_PER_PAGE));

  return (
    <div className={styles.page}>
      <nav className={styles.crumbs}>
        <Link href="/admin/catalog">Catalog</Link>
        <span aria-hidden> / </span>
        <span>Bulk import</span>
      </nav>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>1 · Get a file</h2>
        <p className={styles.help}>
          Every row is one product and carries its full path — service,
          category, subcategory, product. <strong>Slugs are the identity</strong>,
          so renaming is &ldquo;same slug, new name&rdquo;. Import creates and
          updates only; it never deactivates anything. To edit in bulk, export,
          change cells in a spreadsheet, and upload the same file back.
        </p>
        <div className={styles.actions}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void onDownload("template")}
          >
            Download blank template
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void onDownload("export")}
          >
            Export current catalog
          </button>
        </div>
      </section>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>2 · Upload &amp; preview</h2>
        <p className={styles.help}>
          Uploading validates the file against the live catalog and writes
          nothing. You will see exactly what would change before anything is
          applied. <strong>Up to 5,000 rows and 5 MB per file.</strong> Export
          is not capped, so a catalog larger than that has to be re-imported in
          slices — open a service or category in the catalog table first and use
          its Export CSV button, which exports only that subtree.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          className={styles.fileInput}
          disabled={busy !== null}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void onUpload(file);
          }}
        />
        {busy === "upload" && <p className={styles.muted}>Validating…</p>}
      </section>

      {error && (
        <div role="alert" className={styles.error}>
          {error}
        </div>
      )}

      {job && (
        <section className={styles.card}>
          <header className={styles.jobHeader}>
            <div>
              <h2 className={styles.cardTitle}>
                3 · {job.filename}
              </h2>
              <p className={styles.muted}>
                {job.total_rows} row{job.total_rows === 1 ? "" : "s"}
                {job.error_rows > 0 && (
                  <> · <span className={styles.errorText}>{job.error_rows} with errors</span></>
                )}
              </p>
            </div>
            <span className={`${styles.badge} ${styles[`badge_${job.status}`] ?? ""}`}>
              {job.status}
            </span>
          </header>

          {job.failure_reason && (
            <p role="alert" className={styles.errorText}>
              {job.failure_reason}
            </p>
          )}

          <PlanTable
            title={job.applied ? "Applied" : "Planned"}
            plan={job.applied ?? job.plan}
          />

          {job.status === "validated" && job.error_rows === job.total_rows && (
            <p className={styles.errorText}>
              Every row has an error, so there is nothing to apply. Fix the file
              and upload it again.
            </p>
          )}

          {job.status === "applying" && (
            <p className={styles.help}>
              Running on the worker — this page refreshes itself. If it stays
              here (a worker or broker outage), just upload the same file again:
              rows that already landed come back as <em>unchanged</em>, so a
              fresh import only does the work that is left.
            </p>
          )}

          <div className={styles.actions}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!canApply || busy !== null}
              onClick={() => void onApply()}
            >
              {busy === "apply"
                ? "Applying…"
                : job.status === "failed"
                  ? `Resume import (${planTotal(job.plan, "create") + planTotal(job.plan, "update")} changes)`
                  : `Apply ${planTotal(job.plan, "create") + planTotal(job.plan, "update")} changes`}
            </button>
            {job.status === "validated" && (
              <button
                type="button"
                className="btn btn-ghost"
                disabled={busy !== null}
                onClick={() => void onCancel()}
              >
                {busy === "cancel" ? "Discarding…" : "Discard"}
              </button>
            )}
          </div>

          <div className={styles.rowsHeader}>
            <h3 className={styles.subTitle}>Rows</h3>
            <label className={styles.checkLabel}>
              <input
                type="checkbox"
                checked={onlyErrors}
                onChange={(e) => {
                  setOnlyErrors(e.target.checked);
                  setRowPage(1);
                }}
              />
              Errors only
            </label>
          </div>

          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Action</th>
                  <th>Path</th>
                  <th>Product</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={5} className={styles.muted}>
                      {onlyErrors ? "No rows with errors." : "No rows."}
                    </td>
                  </tr>
                )}
                {rows.map((r) => (
                  <tr key={r.id} className={r.action === "error" ? styles.rowError : ""}>
                    <td>{r.line_number}</td>
                    <td>
                      <span className={`${styles.pill} ${styles[`pill_${r.action}`] ?? ""}`}>
                        {r.action}
                      </span>
                    </td>
                    <td className={styles.pathCell}>
                      {[
                        r.data.service_slug,
                        r.data.category_slug,
                        r.data.subcategory_slug,
                      ]
                        .filter(Boolean)
                        .join(" / ") || "—"}
                    </td>
                    <td>{r.data.product_name ?? r.data.product_slug ?? "—"}</td>
                    <td>
                      {r.errors.length > 0 ? (
                        <ul className={styles.errorList}>
                          {r.errors.map((e, i) => (
                            <li key={`${e.column}-${e.code}-${i}`}>
                              <code>{e.column}</code> {e.message}
                            </li>
                          ))}
                        </ul>
                      ) : r.apply_error ? (
                        <span className={styles.errorText}>{r.apply_error}</span>
                      ) : (
                        <span className={styles.muted}>
                          {LEVELS.filter((l) => r.level_plan[l] && r.level_plan[l] !== "noop")
                            .map((l) => `${l}: ${r.level_plan[l]}`)
                            .join(", ") || "no change"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <footer className={styles.pager}>
            <span className={styles.muted}>
              Page {rowPage} of {totalPages} · {rowTotal} rows
            </span>
            <div className={styles.actions}>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={rowPage <= 1}
                onClick={() => setRowPage(rowPage - 1)}
              >
                ‹ Prev
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={rowPage >= totalPages}
                onClick={() => setRowPage(rowPage + 1)}
              >
                Next ›
              </button>
            </div>
          </footer>
        </section>
      )}

      {history.length > 0 && (
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>Recent imports</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>When</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id}>
                    <td>{h.filename}</td>
                    <td>
                      <span className={`${styles.badge} ${styles[`badge_${h.status}`] ?? ""}`}>
                        {h.status}
                      </span>
                    </td>
                    <td className={styles.muted}>
                      {h.total_rows}
                      {h.error_rows > 0 && ` (${h.error_rows} bad)`}
                    </td>
                    <td className={styles.muted}>
                      {new Date(h.created_at).toLocaleString()}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => {
                          setJob(h);
                          setRowPage(1);
                          setOnlyErrors(false);
                        }}
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function PlanTable({ title, plan }: { title: string; plan: ImportPlan }) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.planTable}>
        <caption className={styles.caption}>
          {title} — counts are distinct catalog rows, not CSV lines
        </caption>
        <thead>
          <tr>
            <th />
            <th>Create</th>
            <th>Update</th>
            <th>Unchanged</th>
          </tr>
        </thead>
        <tbody>
          {LEVELS.map((level) => (
            <tr key={level}>
              <th scope="row">{level}</th>
              <td>{plan[level]?.create ?? 0}</td>
              <td>{plan[level]?.update ?? 0}</td>
              <td className={styles.muted}>{plan[level]?.noop ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
