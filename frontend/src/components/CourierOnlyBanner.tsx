"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import styles from "./CourierOnlyBanner.module.css";

/** Home / Stores / Products when no store delivers to the chosen location
 *  but some ship there by courier (the `courier_only` deliverability state). */
export default function CourierOnlyBanner() {
  const t = useTranslations("Deliverability");
  return (
    <section className={styles.banner} role="status">
      <span className={styles.icon} aria-hidden="true">📦</span>
      <p className={styles.message}>{t("courierOnly")}</p>
    </section>
  );
}
