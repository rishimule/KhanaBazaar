"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import Avatar from "@/components/Avatar";
import styles from "./DashboardHeader.module.css";

interface Props {
  fullName?: string;
  storeName: string;
  storePaused: boolean;
  onRefresh: () => void;
  refreshing?: boolean;
  onTogglePause: () => void;
  pauseBusy?: boolean;
  avatarUrl?: string | null;
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function firstName(full?: string): string {
  const n = full?.trim().split(/\s+/)[0];
  return n && n.length > 0 ? n : "there";
}

export default function DashboardHeader({
  fullName,
  storeName,
  storePaused,
  onRefresh,
  refreshing,
  onTogglePause,
  pauseBusy,
  avatarUrl,
}: Props) {
  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <header className={styles.header}>
      <div className={styles.left}>
        <Avatar
          avatarUrl={avatarUrl}
          name={fullName ?? "Seller"}
          seed={fullName ?? "seller"}
          size={48}
        />
        <div>
          <h1 className={styles.greeting}>
            {greeting()}, {firstName(fullName)}
          </h1>
          <p className={styles.subtitle}>
            {storeName && <span className={styles.storeName}>{storeName}</span>}
            <span className={styles.sep}>·</span>
            <span>{today}</span>
            <span className={`${styles.chip} ${storePaused ? styles.chipWarn : styles.chipOk}`}>
              {storePaused ? "Closed" : "Open"}
            </span>
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
          {storePaused ? "Reopen store" : "Close store"}
        </button>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={onRefresh}
          disabled={refreshing}
        >
          ↻ Refresh
        </button>
        <Link href="/seller/inventory/bulk" className={styles.addBtn}>
          + Add product
        </Link>
      </div>
    </header>
  );
}
