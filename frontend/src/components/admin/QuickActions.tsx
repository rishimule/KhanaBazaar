"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useTranslations } from "next-intl";
import styles from "./QuickActions.module.css";

export default function QuickActions() {
  const t = useTranslations("Admin.dashboard");
  const actions = [
    { href: "/admin/orders", icon: "📦", label: t("allOrders"), desc: t("allOrdersDesc") },
    { href: "/admin/catalog", icon: "🗂️", label: t("manageCatalog"), desc: t("manageCatalogDesc") },
    {
      href: "/admin/sellers/applications",
      icon: "✅",
      label: t("reviewApplications"),
      desc: t("reviewApplicationsDesc"),
    },
    {
      href: "/admin/sellers",
      icon: "🏪",
      label: t("approvedSellersAction"),
      desc: t("approvedSellersDesc"),
    },
  ];

  return (
    <section className={styles.card}>
      <h2 className={styles.title}>{t("quickActions")}</h2>
      <div className={styles.list}>
        {actions.map((a) => (
          <Link key={a.href} href={a.href} className={styles.action}>
            <span className={styles.icon}>{a.icon}</span>
            <span className={styles.info}>
              <span className={styles.label}>{a.label}</span>
              <span className={styles.desc}>{a.desc}</span>
            </span>
            <span className={styles.chevron}>›</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
