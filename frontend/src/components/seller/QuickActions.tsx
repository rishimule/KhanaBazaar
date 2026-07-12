"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useTranslations } from "next-intl";
import styles from "./QuickActions.module.css";

const ACTIONS = [
  { href: "/seller/orders", icon: "📦", label: "actionOrdersLabel", desc: "actionOrdersDesc" },
  { href: "/seller/inventory", icon: "🧾", label: "actionInventoryLabel", desc: "actionInventoryDesc" },
  { href: "/seller/settings", icon: "⚙️", label: "actionSettingsLabel", desc: "actionSettingsDesc" },
] as const;

export default function QuickActions() {
  const t = useTranslations("Seller.dashboard");
  return (
    <section className={styles.card}>
      <h2 className={styles.title}>{t("quickActions")}</h2>
      <div className={styles.list}>
        {ACTIONS.map((a) => (
          <Link key={a.href} href={a.href} className={styles.action}>
            <span className={styles.icon}>{a.icon}</span>
            <span className={styles.info}>
              <span className={styles.label}>{t(a.label)}</span>
              <span className={styles.desc}>{t(a.desc)}</span>
            </span>
            <span className={styles.chevron}>›</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
