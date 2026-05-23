"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useTranslations } from "next-intl";
import { usePWAInstall } from "./usePWAInstall";
import styles from "./pwa-install.module.css";

export default function AccountInstallBanner() {
  const t = useTranslations("Account.dashboard");
  const { canShowEntry, install } = usePWAInstall();

  if (!canShowEntry) return null;

  return (
    <button
      type="button"
      className={styles.banner}
      onClick={() => install("account_shortcut")}
    >
      <span className={styles.bannerIcon} aria-hidden="true">📲</span>
      <span className={styles.bannerText}>
        <span className={styles.bannerTitle}>{t("installAppTitle")}</span>
        <span className={styles.bannerSubtitle}>{t("installAppSubtitle")}</span>
      </span>
      <span className={styles.bannerChevron} aria-hidden="true">›</span>
    </button>
  );
}
