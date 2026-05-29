"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import styles from "./DashboardHeader.module.css";

interface Props {
  fullName?: string;
  storeName: string;
  storeActive: boolean;
  pinConfirmed: boolean;
  onRefresh: () => void;
  refreshing?: boolean;
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
  storeActive,
  pinConfirmed,
  onRefresh,
  refreshing,
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
        <h1 className={styles.greeting}>
          {greeting()}, {firstName(fullName)}
        </h1>
        <p className={styles.subtitle}>
          {storeName && <span>{storeName}</span>}
          <span className={styles.sep}>·</span>
          <span>{today}</span>
          <span className={`${styles.chip} ${storeActive ? styles.chipOk : styles.chipWarn}`}>
            {storeActive ? "Active" : "Inactive"}
          </span>
          <span className={`${styles.chip} ${pinConfirmed ? styles.chipOk : styles.chipWarn}`}>
            {pinConfirmed ? "PIN confirmed" : "PIN not confirmed"}
          </span>
        </p>
      </div>
      <div className={styles.actions}>
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
