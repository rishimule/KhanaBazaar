"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useTranslations } from "next-intl";
import type { OrderStatusCounts } from "@/types";
import styles from "./OrderStatusDonut.module.css";

interface Props {
  counts: OrderStatusCounts;
}

const SEGMENTS: { key: keyof OrderStatusCounts; label: string; color: string }[] = [
  { key: "delivered", label: "donutDelivered", color: "var(--color-success)" },
  { key: "packed", label: "donutPacked", color: "var(--color-info)" },
  { key: "dispatched", label: "donutDispatched", color: "var(--color-accent-500)" },
  { key: "pending", label: "donutPending", color: "var(--color-warning)" },
  { key: "cancelled", label: "donutCancelled", color: "var(--color-neutral-400)" },
];

const R = 54;
const STROKE = 16;
const C = 2 * Math.PI * R;

export default function OrderStatusDonut({ counts }: Props) {
  const t = useTranslations("Seller.dashboard");
  const total = SEGMENTS.reduce((s, seg) => s + counts[seg.key], 0);
  let offset = 0;

  return (
    <section className={styles.card}>
      <h2 className={styles.title}>{t("orderStatus")}</h2>
      <div className={styles.body}>
        <svg className={styles.svg} viewBox="0 0 140 140">
          <circle cx="70" cy="70" r={R} fill="none" stroke="var(--color-neutral-100)" strokeWidth={STROKE} />
          {total > 0 &&
            SEGMENTS.map((seg) => {
              const val = counts[seg.key];
              if (val === 0) return null;
              const len = (val / total) * C;
              const dash = `${len} ${C - len}`;
              const el = (
                <circle
                  key={seg.key}
                  cx="70"
                  cy="70"
                  r={R}
                  fill="none"
                  stroke={seg.color}
                  strokeWidth={STROKE}
                  strokeDasharray={dash}
                  strokeDashoffset={-offset}
                  transform="rotate(-90 70 70)"
                />
              );
              offset += len;
              return el;
            })}
          <text x="70" y="66" textAnchor="middle" className={styles.centerNum}>
            {total}
          </text>
          <text x="70" y="84" textAnchor="middle" className={styles.centerLabel}>
            {t("donutOrders")}
          </text>
        </svg>
        <ul className={styles.legend}>
          {SEGMENTS.map((seg) => (
            <li key={seg.key} className={styles.legendItem}>
              <span className={styles.dot} style={{ background: seg.color }} />
              <span className={styles.legendLabel}>{t(seg.label)}</span>
              <span className={styles.legendVal}>{counts[seg.key]}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
