"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useTranslations } from "next-intl";
import type { OrderServiceStat } from "@/types";
import styles from "./OrdersByService.module.css";

interface Props {
  services: OrderServiceStat[];
}

// Stable palette cycled by row index.
const COLORS = [
  "var(--color-primary)",
  "var(--color-accent-500)",
  "var(--color-info)",
  "var(--color-success)",
  "var(--color-warning)",
  "#8b5cf6",
];

export default function OrdersByService({ services }: Props) {
  const t = useTranslations("Admin.dashboard");
  const total = services.reduce((s, x) => s + x.count, 0);
  const max = Math.max(1, ...services.map((s) => s.count));
  const top = services[0] ?? null;

  return (
    <section className={styles.card}>
      <h2 className={styles.title}>{t("ordersByService")}</h2>

      {services.length === 0 ? (
        <p className={styles.empty}>{t("noOrdersService")}</p>
      ) : (
        <ul className={styles.list}>
          {services.map((s, i) => {
            const color = COLORS[i % COLORS.length];
            const pct = Math.round((s.count / max) * 100);
            return (
              <li key={s.service_id} className={styles.row}>
                <div className={styles.rowTop}>
                  <span className={styles.name}>
                    <span className={styles.dot} style={{ background: color }} />
                    {s.service_name}
                  </span>
                  <span className={styles.count}>{s.count}</span>
                </div>
                <div className={styles.track}>
                  <div className={styles.fill} style={{ width: `${pct}%`, background: color }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {services.length > 0 && (
        <div className={styles.footer}>
          <span>✓ {t("ordersTotal", { count: total })}</span>
          {top && <span>{t("topService", { name: top.service_name, count: top.count })}</span>}
        </div>
      )}
    </section>
  );
}
