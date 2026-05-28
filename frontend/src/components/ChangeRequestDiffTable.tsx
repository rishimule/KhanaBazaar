"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import styles from "./ChangeRequestDiffTable.module.css";

interface Props {
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  beforeLabel?: string;
  afterLabel?: string;
}

function format(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/**
 * Side-by-side diff of two JSON-ish records (current vs proposed).
 * Highlights rows where the values differ; hides unchanged rows by default
 * and exposes a "Show unchanged" toggle when there are any.
 */
export default function ChangeRequestDiffTable({
  before,
  after,
  beforeLabel = "Current",
  afterLabel = "Proposed",
}: Props) {
  const [showUnchanged, setShowUnchanged] = useState(false);
  const keys = Array.from(
    new Set([...Object.keys(before), ...Object.keys(after)]),
  );
  const rows = keys.map((k) => ({
    key: k,
    before: before[k],
    after: after[k],
    changed: JSON.stringify(before[k]) !== JSON.stringify(after[k]),
  }));
  const visible = showUnchanged ? rows : rows.filter((r) => r.changed);
  const hasUnchanged = rows.some((r) => !r.changed);

  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Field</th>
            <th>{beforeLabel}</th>
            <th>{afterLabel}</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((r) => (
            <tr key={r.key} className={r.changed ? styles.changed : undefined}>
              <td>{r.key}</td>
              <td>{format(r.before)}</td>
              <td>{format(r.after)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {hasUnchanged && (
        <button
          type="button"
          className={styles.toggle}
          onClick={() => setShowUnchanged((v) => !v)}
        >
          {showUnchanged ? "Hide unchanged" : "Show unchanged"}
        </button>
      )}
    </div>
  );
}
