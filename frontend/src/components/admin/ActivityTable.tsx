"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useTranslations } from "next-intl";
import { Fragment, useState } from "react";
import type { AdminActionLog } from "@/types";
import styles from "./ActivityTable.module.css";

type Translator = ReturnType<typeof useTranslations>;

interface Props {
  rows: AdminActionLog[];
  hasMore: boolean;
  loading?: boolean;
  onLoadMore: () => void;
}

const ACTION_KEYS: Record<string, string> = {
  "inventory.create": "actionInventoryCreate",
  "inventory.update": "actionInventoryUpdate",
  "inventory.delete": "actionInventoryDelete",
  "inventory.bulk_update": "actionInventoryBulkUpdate",
  "order.transition": "actionOrderTransition",
  "order.cancel": "actionOrderCancel",
  "order.rewind": "actionOrderRewind",
  "order.refund": "actionOrderRefund",
  "order.address_override": "actionOrderAddressOverride",
};

function actionLabel(t: Translator, action: string): string {
  const key = ACTION_KEYS[action];
  return key ? t(`activityTable.${key}`) : action;
}

function describeTarget(t: Translator, row: AdminActionLog): string {
  const after = row.after_json ?? {};
  const before = row.before_json ?? {};
  if (row.target_type === "inventory") {
    const pid = (after as Record<string, unknown>).product_id ?? (before as Record<string, unknown>).product_id;
    return pid
      ? t("activityTable.targetInventoryWithProduct", { id: row.target_id, productId: String(pid) })
      : t("activityTable.targetInventory", { id: row.target_id });
  }
  if (row.target_type === "order") return t("activityTable.targetOrder", { id: row.target_id });
  return `${row.target_type} #${row.target_id}`;
}

function shortTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

export default function ActivityTable({
  rows,
  hasMore,
  loading,
  onLoadMore,
}: Props) {
  const t = useTranslations("Shared");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (rows.length === 0) {
    return (
      <div className={styles.empty}>
        {t("activityTable.empty")}
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>{t("activityTable.colTime")}</th>
            <th>{t("activityTable.colAction")}</th>
            <th>{t("activityTable.colTarget")}</th>
            <th>{t("activityTable.colAdmin")}</th>
            <th>{t("activityTable.colReason")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isOpen = expanded.has(row.id);
            const pillCls = styles[row.target_type] ?? styles.unknown;
            return (
              <Fragment key={row.id}>
                <tr className={styles.row}>
                  <td className={styles.time}>{shortTime(row.created_at)}</td>
                  <td>
                    <span className={`${styles.pill} ${pillCls}`}>
                      {actionLabel(t, row.action)}
                    </span>
                  </td>
                  <td>{describeTarget(t, row)}</td>
                  <td className={styles.admin}>{row.admin_email}</td>
                  <td className={styles.reason}>{row.reason ?? "—"}</td>
                  <td>
                    <button
                      type="button"
                      className={styles.toggle}
                      onClick={() => toggle(row.id)}
                    >
                      {isOpen ? t("activityTable.hide") : t("activityTable.diff")}
                    </button>
                  </td>
                </tr>
                {isOpen && (
                  <tr className={styles.diffRow}>
                    <td colSpan={6}>
                      <div className={styles.diffGrid}>
                        <pre className={styles.diff}>
                          <strong>{t("activityTable.before")}</strong>
                          {"\n"}
                          {JSON.stringify(row.before_json, null, 2)}
                        </pre>
                        <pre className={styles.diff}>
                          <strong>{t("activityTable.after")}</strong>
                          {"\n"}
                          {JSON.stringify(row.after_json, null, 2)}
                        </pre>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      {hasMore && (
        <button
          type="button"
          className={styles.loadMore}
          disabled={loading}
          onClick={onLoadMore}
        >
          {loading ? t("activityTable.loading") : t("activityTable.loadMore")}
        </button>
      )}
    </div>
  );
}
