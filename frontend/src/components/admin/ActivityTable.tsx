"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Fragment, useState } from "react";
import { GROUP_LABEL } from "@/lib/changeRequests";
import type {
  AdminActionLog,
  SellerProfileChangeGroup,
} from "@/types";
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
  profile_cr_approve: "actionProfileCRApprove",
  profile_cr_approve_with_edits: "actionProfileCRApproveWithEdits",
  profile_cr_request_changes: "actionProfileCRRequestChanges",
  profile_cr_reject: "actionProfileCRReject",
};

const PROFILE_CR_ACTIONS = new Set<string>([
  "profile_cr_approve",
  "profile_cr_approve_with_edits",
  "profile_cr_request_changes",
  "profile_cr_reject",
]);

function getString(
  source: Record<string, unknown> | null,
  key: string,
): string | null {
  if (!source) return null;
  const value = source[key];
  return typeof value === "string" ? value : null;
}

function groupLabelFromRow(row: AdminActionLog): string {
  const raw =
    getString(row.before_json, "group") ?? getString(row.after_json, "group");
  if (raw && raw in GROUP_LABEL) {
    return GROUP_LABEL[raw as SellerProfileChangeGroup];
  }
  return raw ?? "—";
}

function crIdFromRow(row: AdminActionLog): string | null {
  return getString(row.before_json, "cr_id") ?? getString(row.after_json, "cr_id");
}

function actionLabel(t: Translator, action: string): string {
  const key = ACTION_KEYS[action];
  return key ? t(`activityTable.${key}`) : action;
}

function describeTarget(t: Translator, row: AdminActionLog): React.ReactNode {
  const after = row.after_json ?? {};
  const before = row.before_json ?? {};
  if (PROFILE_CR_ACTIONS.has(row.action)) {
    const group = groupLabelFromRow(row);
    const crId = crIdFromRow(row);
    const label = `${group} change request`;
    if (crId) {
      return (
        <Link
          href={`/admin/sellers/${row.target_seller_id}/requests/${crId}`}
          className={styles.targetLink}
        >
          {label}
        </Link>
      );
    }
    return label;
  }
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
