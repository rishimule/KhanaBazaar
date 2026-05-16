"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useState } from "react";
import type { AdminActionLog } from "@/types";
import styles from "./ActivityTable.module.css";

interface Props {
  rows: AdminActionLog[];
  hasMore: boolean;
  loading?: boolean;
  onLoadMore: () => void;
}

function actionLabel(action: string): string {
  const map: Record<string, string> = {
    "inventory.create": "Added product",
    "inventory.update": "Updated product",
    "inventory.delete": "Deleted product",
    "inventory.bulk_update": "Bulk updated",
    "order.transition": "Moved status",
    "order.cancel": "Cancelled order",
    "order.rewind": "Rewound status",
    "order.refund": "Refunded payment",
    "order.address_override": "Overrode address",
  };
  return map[action] ?? action;
}

function describeTarget(row: AdminActionLog): string {
  const after = row.after_json ?? {};
  const before = row.before_json ?? {};
  if (row.target_type === "inventory") {
    const pid = (after as Record<string, unknown>).product_id ?? (before as Record<string, unknown>).product_id;
    return `Inventory #${row.target_id}${pid ? ` (product ${pid})` : ""}`;
  }
  if (row.target_type === "order") return `Order #${row.target_id}`;
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
        No admin activity for this seller yet.
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Time</th>
            <th>Action</th>
            <th>Target</th>
            <th>Admin</th>
            <th>Reason</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isOpen = expanded.has(row.id);
            return (
              <>
                <tr key={row.id} className={styles.row}>
                  <td className={styles.time}>{shortTime(row.created_at)}</td>
                  <td>
                    <span className={`${styles.pill} ${styles[row.target_type]}`}>
                      {actionLabel(row.action)}
                    </span>
                  </td>
                  <td>{describeTarget(row)}</td>
                  <td className={styles.admin}>{row.admin_email}</td>
                  <td className={styles.reason}>{row.reason ?? "—"}</td>
                  <td>
                    <button
                      type="button"
                      className={styles.toggle}
                      onClick={() => toggle(row.id)}
                    >
                      {isOpen ? "Hide" : "Diff"}
                    </button>
                  </td>
                </tr>
                {isOpen && (
                  <tr key={`${row.id}-diff`} className={styles.diffRow}>
                    <td colSpan={6}>
                      <div className={styles.diffGrid}>
                        <pre className={styles.diff}>
                          <strong>before</strong>
                          {"\n"}
                          {JSON.stringify(row.before_json, null, 2)}
                        </pre>
                        <pre className={styles.diff}>
                          <strong>after</strong>
                          {"\n"}
                          {JSON.stringify(row.after_json, null, 2)}
                        </pre>
                      </div>
                    </td>
                  </tr>
                )}
              </>
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
          {loading ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}
