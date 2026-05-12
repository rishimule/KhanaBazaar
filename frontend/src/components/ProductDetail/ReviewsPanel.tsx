// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";
import { useTranslations } from "next-intl";
import styles from "./ReviewsPanel.module.css";

interface Props {
  storeName: string;
}

export default function ReviewsPanel({ storeName }: Props) {
  const t = useTranslations("Product");
  return (
    <section className={styles.panel} aria-label={t("reviewsComingSoon")}>
      <h3 className={styles.title}>{t("reviewsComingSoon")}</h3>
      <p className={styles.body}>
        {t("reviewsPlaceholder", { storeName })}
      </p>
    </section>
  );
}
