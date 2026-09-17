"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { bulkSetActive, downloadCatalogExport } from "@/lib/catalogImport";
import type { CatalogEntity, EntityKind } from "@/types";
import { useCatalogList } from "../_hooks/useCatalogList";
import { useEntityMutation } from "../_hooks/useEntityMutation";
import { BulkStatusConfirm } from "./BulkStatusConfirm";
import { DeactivateConfirm } from "./DeactivateConfirm";
import { EditModal } from "./EditModal";
import styles from "./CatalogTable.module.css";

interface Props {
  entity: EntityKind;
  parentId?: number;
  /** When listing subcategories: the service that owns the parent category.
   * Passed to EditModal so the subcategory's parent picker is scoped to
   * the right service. */
  serviceContext?: number;
  onRowOpen?: (row: CatalogEntity) => void;
}

const PAGE_SIZE = 25;
type ActiveFilter = "true" | "false" | "all";

export function CatalogTable({
  entity,
  parentId,
  serviceContext,
  onRowOpen,
}: Props) {
  const t = useTranslations("Admin.catalog");
  const tc = useTranslations("Admin.common");
  const entityName = t(`entity.${entity}`);
  const entityNamePlural = t(`entityPlural.${entity}`);
  const [q, setQ] = useState("");
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>("true");
  const [page, setPage] = useState(1);
  const [modalState, setModalState] = useState<
    { mode: "create" } | { mode: "edit"; row: CatalogEntity } | null
  >(null);
  const [confirmRow, setConfirmRow] = useState<CatalogEntity | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkTarget, setBulkTarget] = useState<boolean | null>(null);
  const [bulkPending, setBulkPending] = useState(false);
  const [bulkNote, setBulkNote] = useState<string | null>(null);
  const mut = useEntityMutation(entity);
  const { token } = useAuth();

  const isActive =
    activeFilter === "all" ? null : activeFilter === "true";

  const params = {
    q: q || undefined,
    is_active: isActive,
    page,
    page_size: PAGE_SIZE,
    ...(entity === "category" && parentId ? { service_id: parentId } : {}),
    ...(entity === "subcategory" && parentId ? { category_id: parentId } : {}),
    ...(entity === "product" && parentId ? { subcategory_id: parentId } : {}),
  };

  const { data, loading, error, refetch } = useCatalogList(entity, params);
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  // Selection is per-view: changing level, parent, page, query or status filter
  // would otherwise leave ids selected that are no longer on screen, and the
  // bulk bar would act on rows the operator cannot see.
  useEffect(() => {
    setSelected(new Set());
    setBulkNote(null);
  }, [entity, parentId, page, q, activeFilter]);

  const visibleIds = useMemo(
    () => (data?.items ?? []).map((r) => r.id),
    [data],
  );
  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every((id) => selected.has(id));
  const selectedRows = (data?.items ?? []).filter((r) => selected.has(r.id));
  const selectedChildCount = selectedRows.reduce(
    (sum, r) => sum + (r.child_count ?? 0),
    0,
  );

  function toggleRow(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAllVisible() {
    setSelected(allVisibleSelected ? new Set() : new Set(visibleIds));
  }

  async function runBulk(nextActive: boolean) {
    setBulkPending(true);
    setBulkNote(null);
    try {
      const result = await bulkSetActive(
        entity,
        [...selected],
        nextActive,
        token,
      );
      setBulkNote(
        t("bulkResult", {
          updated: result.updated,
          unchanged: result.unchanged.length,
        }),
      );
      setSelected(new Set());
      setBulkTarget(null);
      refetch();
    } catch {
      setBulkNote(t("bulkFailed"));
    } finally {
      setBulkPending(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <header className={styles.toolbar}>
        <input
          type="search"
          className={styles.search}
          placeholder={t("searchPlaceholder")}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
        <select
          className={styles.filter}
          value={activeFilter}
          onChange={(e) => {
            setActiveFilter(e.target.value as ActiveFilter);
            setPage(1);
          }}
        >
          <option value="true">{t("statusActive")}</option>
          <option value="false">{t("statusInactive")}</option>
          <option value="all">{t("statusAll")}</option>
        </select>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => setModalState({ mode: "create" })}
        >
          {t("addEntity", { entity: entityName })}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => {
            void downloadCatalogExport(
              {
                serviceId: entity === "category" ? parentId : serviceContext,
                categoryId: entity === "subcategory" ? parentId : undefined,
                subcategoryId: entity === "product" ? parentId : undefined,
                includeInactive: activeFilter !== "true",
              },
              token,
            );
          }}
        >
          {t("exportCsv")}
        </button>
        <Link href="/admin/catalog/import" className="btn btn-secondary">
          {t("importCsv")}
        </Link>
      </header>

      {selected.size > 0 && (
        <div className={styles.bulkBar}>
          <span className={styles.bulkCount}>
            {t("nSelected", { count: selected.size })}
          </span>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => setBulkTarget(false)}
          >
            {t("bulkDeactivate")}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => setBulkTarget(true)}
          >
            {t("bulkActivate")}
          </button>
          <button
            type="button"
            className={styles.bulkClear}
            onClick={() => setSelected(new Set())}
          >
            {t("clearSelection")}
          </button>
        </div>
      )}

      {bulkNote && (
        <p role="status" className={styles.bulkNote}>
          {bulkNote}
        </p>
      )}

      {error && (
        <div role="alert" className={styles.error}>
          {t("loadFailed")} <button onClick={refetch}>{tc("retry")}</button>
        </div>
      )}

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.checkCol}>
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  disabled={visibleIds.length === 0}
                  onChange={toggleAllVisible}
                  aria-label={t("selectAllAria")}
                />
              </th>
              <th aria-label={t("colImage")} />
              <th>{t("colName")}</th>
              <th>{t("colSlug")}</th>
              <th>{t("colActive")}</th>
              {entity !== "product" && <th>{t("colChildren")}</th>}
              <th>{t("colTranslations")}</th>
              <th className={styles.actionsCol}>{t("colActions")}</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={8} className={styles.muted}>
                  {tc("loading")}
                </td>
              </tr>
            )}
            {!loading && data && data.items.length === 0 && (
              <tr>
                <td colSpan={8} className={styles.muted}>
                  {t("emptyEntity", { entity: entityNamePlural })}
                </td>
              </tr>
            )}
            {!loading &&
              data?.items.map((row) => (
                <tr key={row.id} className={selected.has(row.id) ? styles.rowSelected : ""}>
                  <td className={styles.checkCol}>
                    <input
                      type="checkbox"
                      checked={selected.has(row.id)}
                      onChange={() => toggleRow(row.id)}
                      aria-label={t("selectRowAria", { name: row.name })}
                    />
                  </td>
                  <td className={styles.imgCell}>
                    {row.image_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={row.image_url} alt="" referrerPolicy="no-referrer" />
                    ) : (
                      <span aria-hidden className={styles.imgPlaceholder}>—</span>
                    )}
                  </td>
                  <td className={styles.nameCell}>
                    {entity !== "product" && onRowOpen ? (
                      <button
                        type="button"
                        className={styles.nameLink}
                        onClick={() => onRowOpen(row)}
                      >
                        {row.name}
                      </button>
                    ) : (
                      row.name
                    )}
                  </td>
                  <td className={styles.slugCell}>{row.slug}</td>
                  <td>
                    {row.is_active ? (
                      <span className={`${styles.badge} ${styles.badgeActive}`}>{t("statusActive")}</span>
                    ) : (
                      <span className={`${styles.badge} ${styles.badgeInactive}`}>{t("statusInactive")}</span>
                    )}
                  </td>
                  {entity !== "product" && (
                    <td className={styles.muted}>{row.child_count ?? 0}</td>
                  )}
                  <td>
                    <span className={styles.chipRow}>
                      {row.translations.map((t) => (
                        <span key={t.language_code} className={styles.chip}>
                          {t.language_code.toUpperCase()}
                        </span>
                      ))}
                    </span>
                  </td>
                  <td className={styles.actionsCell}>
                    <div className={styles.actions}>
                      {entity !== "product" && onRowOpen && (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          onClick={() => onRowOpen(row)}
                        >
                          {t("open")}
                        </button>
                      )}
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => setModalState({ mode: "edit", row })}
                      >
                        {tc("edit")}
                      </button>
                      {row.is_active ? (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          onClick={() => setConfirmRow(row)}
                        >
                          {t("deactivate")}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          onClick={async () => {
                            await mut.update(row.id, { is_active: true });
                            refetch();
                          }}
                        >
                          {t("activate")}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      <footer className={styles.pagination}>
        <span className={styles.muted}>
          {t("pageInfo", { page, totalPages, total: data?.total ?? 0 })}
        </span>
        <div className={styles.pagerBtns}>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            {t("prev")}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            {t("next")}
          </button>
        </div>
      </footer>

      {modalState && (
        <EditModal
          entity={entity}
          mode={modalState.mode}
          initial={modalState.mode === "edit" ? modalState.row : undefined}
          parentId={parentId}
          serviceContext={serviceContext}
          onClose={() => setModalState(null)}
          onSaved={refetch}
        />
      )}

      {bulkTarget !== null && (
        <BulkStatusConfirm
          entity={entity}
          count={selected.size}
          childCount={selectedChildCount}
          nextActive={bulkTarget}
          pending={bulkPending}
          onCancel={() => setBulkTarget(null)}
          onConfirm={() => void runBulk(bulkTarget)}
        />
      )}

      {confirmRow && (
        <DeactivateConfirm
          entity={entity}
          name={confirmRow.name}
          childCount={confirmRow.child_count ?? 0}
          pending={mut.pending}
          onCancel={() => setConfirmRow(null)}
          onConfirm={async () => {
            await mut.remove(confirmRow.id);
            setConfirmRow(null);
            refetch();
          }}
        />
      )}
    </div>
  );
}
