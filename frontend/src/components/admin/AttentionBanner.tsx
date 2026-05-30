"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useTranslations } from "next-intl";
import styles from "./AttentionBanner.module.css";

interface Props {
  pendingApplications: number;
  openChangeRequests: number;
}

export default function AttentionBanner({ pendingApplications, openChangeRequests }: Props) {
  const t = useTranslations("Admin.dashboard");
  if (pendingApplications <= 0 && openChangeRequests <= 0) return null;

  return (
    <div className={styles.wrap}>
      {pendingApplications > 0 && (
        <Link href="/admin/sellers/applications" className={styles.card}>
          <span className={styles.icon}>📥</span>
          <span className={styles.text}>
            {t("bannerAppsAwaiting", { count: pendingApplications })}
          </span>
          <span className={styles.arrow}>→</span>
        </Link>
      )}
      {openChangeRequests > 0 && (
        <Link href="/admin/change-requests" className={styles.card}>
          <span className={styles.icon}>✉️</span>
          <span className={styles.text}>
            {t("bannerCrsOpen", { count: openChangeRequests })}
          </span>
          <span className={styles.arrow}>→</span>
        </Link>
      )}
    </div>
  );
}
