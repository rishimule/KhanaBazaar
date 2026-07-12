"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useTranslations } from "next-intl";
import Avatar from "@/components/Avatar";
import styles from "./DashboardHeader.module.css";

interface Props {
  fullName?: string;
  storeName: string;
  storePaused: boolean;
  isPremium?: boolean;
  onRefresh: () => void;
  refreshing?: boolean;
  onTogglePause: () => void;
  pauseBusy?: boolean;
  avatarUrl?: string | null;
}

function greetingKey(): "greetingMorning" | "greetingAfternoon" | "greetingEvening" {
  const h = new Date().getHours();
  if (h < 12) return "greetingMorning";
  if (h < 17) return "greetingAfternoon";
  return "greetingEvening";
}

export default function DashboardHeader({
  fullName,
  storeName,
  storePaused,
  isPremium,
  onRefresh,
  refreshing,
  onTogglePause,
  pauseBusy,
  avatarUrl,
}: Props) {
  const t = useTranslations("Seller.dashboard");
  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  const name = fullName?.trim().split(/\s+/)[0] || t("greetingFallback");

  return (
    <header className={styles.header}>
      <div className={styles.left}>
        <Avatar
          avatarUrl={avatarUrl}
          name={fullName ?? t("sellerFallback")}
          seed={fullName ?? "seller"}
          size={48}
        />
        <div>
          <h1 className={styles.greeting}>
            {t(greetingKey())}, {name}
          </h1>
          <p className={styles.subtitle}>
            {storeName && <span className={styles.storeName}>{storeName}</span>}
            <span className={styles.sep}>·</span>
            <span>{today}</span>
            <span className={`${styles.chip} ${storePaused ? styles.chipWarn : styles.chipOk}`}>
              {storePaused ? t("statusClosed") : t("statusOpen")}
            </span>
            {isPremium && (
              <span className={`badge badge--member ${styles.premiumPill}`}>👑 {t("premiumPill")}</span>
            )}
          </p>
        </div>
      </div>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={onTogglePause}
          disabled={pauseBusy}
        >
          {storePaused ? t("reopenStore") : t("closeStore")}
        </button>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={onRefresh}
          disabled={refreshing}
        >
          ↻ {t("refresh")}
        </button>
        <Link href="/seller/inventory/bulk" className={styles.addBtn}>
          + {t("addProduct")}
        </Link>
      </div>
    </header>
  );
}
