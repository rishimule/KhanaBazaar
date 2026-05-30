"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useTranslations } from "next-intl";
import styles from "./DashboardHeader.module.css";

interface Props {
  reviewQueue: number;
  onRefresh: () => void;
  refreshing?: boolean;
}

function greetingKey(): "greetingMorning" | "greetingAfternoon" | "greetingEvening" {
  const h = new Date().getHours();
  if (h < 12) return "greetingMorning";
  if (h < 17) return "greetingAfternoon";
  return "greetingEvening";
}

export default function DashboardHeader({ reviewQueue, onRefresh, refreshing }: Props) {
  const t = useTranslations("Admin.dashboard");
  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <header className={styles.header}>
      <div className={styles.left}>
        <h1 className={styles.greeting}>{t(greetingKey())}</h1>
        <p className={styles.subtitle}>
          <span>{t("platformOverview")}</span>
          <span className={styles.sep}>·</span>
          <span>{today}</span>
          <span className={`${styles.chip} ${styles.chipOk}`}>{t("systemsNormal")}</span>
        </p>
      </div>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={onRefresh}
          disabled={refreshing}
        >
          ↻ {t("refresh")}
        </button>
        <Link href="/admin/sellers/applications" className={styles.addBtn}>
          {t("reviewQueueCount", { count: reviewQueue })}
        </Link>
      </div>
    </header>
  );
}
