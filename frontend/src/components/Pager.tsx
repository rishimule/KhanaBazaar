// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import styles from "./Pager.module.css";

interface PagerLabels {
  prev: string;
  next: string;
  /** Receives 1-based from/to and total; returns the summary line. */
  summary: (from: number, to: number, total: number) => string;
}

const DEFAULT_LABELS: PagerLabels = {
  prev: "‹ Prev",
  next: "Next ›",
  summary: (from, to, total) => `Showing ${from}–${to} of ${total}`,
};

interface PagerProps {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
  labels?: Partial<PagerLabels>;
}

/** Build a windowed page list like [1, "…", 4, 5, 6, "…", 12]. */
function pageWindow(page: number, totalPages: number): (number | "…")[] {
  const out: (number | "…")[] = [];
  const lo = Math.max(2, page - 1);
  const hi = Math.min(totalPages - 1, page + 1);
  out.push(1);
  if (lo > 2) out.push("…");
  for (let n = lo; n <= hi; n++) out.push(n);
  if (hi < totalPages - 1) out.push("…");
  if (totalPages > 1) out.push(totalPages);
  return out;
}

export default function Pager({ page, pageSize, total, onPage, labels }: PagerProps) {
  const l = { ...DEFAULT_LABELS, ...labels };
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <nav className={styles.pager} aria-label="Pagination">
      <span className={styles.summary}>{l.summary(from, to, total)}</span>
      <div className={styles.controls}>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          {l.prev}
        </button>
        {pageWindow(page, totalPages).map((n, i) =>
          n === "…" ? (
            <span key={`gap-${i}`} className={styles.gap}>
              …
            </span>
          ) : (
            <button
              key={n}
              type="button"
              className={n === page ? styles.pageActive : styles.page}
              aria-current={n === page ? "page" : undefined}
              onClick={() => onPage(n)}
            >
              {n}
            </button>
          ),
        )}
        <button
          type="button"
          className="btn btn-secondary"
          disabled={page >= totalPages}
          onClick={() => onPage(page + 1)}
        >
          {l.next}
        </button>
      </div>
    </nav>
  );
}
