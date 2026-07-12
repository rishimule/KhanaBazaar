"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { InventoryServiceStat, TopSubcategory } from "@/types";
import styles from "./InventoryByService.module.css";

interface Props {
  services: InventoryServiceStat[];
  outOfStock: number;
  topSubcategory: TopSubcategory | null;
}

export default function InventoryByService({ services, outOfStock, topSubcategory }: Props) {
  const t = useTranslations("Seller.dashboard");
  return (
    <section className={styles.card}>
      <div className={styles.head}>
        <h2 className={styles.title}>{t("inventoryByService")}</h2>
        <Link href="/seller/inventory" className={styles.manage}>
          {t("manage")} →
        </Link>
      </div>

      {services.length === 0 ? (
        <p className={styles.empty}>{t("noProductsYet")}</p>
      ) : (
        <ul className={styles.list}>
          {services.map((s) => {
            const pct = s.total > 0 ? Math.round((s.in_stock / s.total) * 100) : 0;
            return (
              <li key={s.service_id} className={styles.row}>
                <div className={styles.rowTop}>
                  <span className={styles.name}>{s.service_name}</span>
                  <span className={styles.count}>
                    {s.in_stock} <span className={styles.total}>/ {s.total}</span>
                  </span>
                </div>
                <div className={styles.track}>
                  <div className={styles.fill} style={{ width: `${pct}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <div className={styles.footer}>
        <span className={outOfStock > 0 ? styles.warn : styles.ok}>
          {outOfStock > 0
            ? `⚠ ${t("outOfStockN", { count: outOfStock })}`
            : `✓ ${t("stockHealthy")}`}
        </span>
        {topSubcategory && (
          <span className={styles.top}>
            {t("topSubcategory", { name: topSubcategory.name, count: topSubcategory.count })}
          </span>
        )}
      </div>
    </section>
  );
}
