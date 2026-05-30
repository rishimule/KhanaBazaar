"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useTranslations } from "next-intl";
import styles from "./ApplicationPipeline.module.css";

interface Props {
  approved: number;
  pending: number;
  rejected: number;
}

const R = 54;
const STROKE = 16;
const C = 2 * Math.PI * R;

export default function ApplicationPipeline({ approved, pending, rejected }: Props) {
  const t = useTranslations("Admin.dashboard");
  const segments = [
    { key: "approved", label: t("pipelineApproved"), value: approved, color: "var(--color-success)" },
    { key: "pending", label: t("pipelinePending"), value: pending, color: "var(--color-warning)" },
    { key: "rejected", label: t("pipelineRejected"), value: rejected, color: "var(--color-error)" },
  ];
  const total = segments.reduce((s, seg) => s + seg.value, 0);
  let offset = 0;

  return (
    <section className={styles.card}>
      <div className={styles.head}>
        <h2 className={styles.title}>{t("applicationPipeline")}</h2>
        <Link href="/admin/sellers/applications" className={styles.open}>
          {t("open")} →
        </Link>
      </div>
      <div className={styles.body}>
        <svg className={styles.svg} viewBox="0 0 140 140">
          <circle cx="70" cy="70" r={R} fill="none" stroke="var(--color-neutral-100)" strokeWidth={STROKE} />
          {total > 0 &&
            segments.map((seg) => {
              if (seg.value === 0) return null;
              const len = (seg.value / total) * C;
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
            {t("pipelineTotal")}
          </text>
        </svg>
        <ul className={styles.legend}>
          {segments.map((seg) => (
            <li key={seg.key} className={styles.legendItem}>
              <span className={styles.dot} style={{ background: seg.color }} />
              <span className={styles.legendLabel}>{seg.label}</span>
              <span className={styles.legendVal}>{seg.value}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
