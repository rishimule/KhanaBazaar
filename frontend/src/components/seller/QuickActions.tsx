"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import styles from "./QuickActions.module.css";

const ACTIONS = [
  { href: "/seller/orders", icon: "📦", label: "Manage orders", desc: "Update status, handle cancellations" },
  { href: "/seller/inventory", icon: "🧾", label: "Manage inventory", desc: "Add, edit or remove products" },
  { href: "/seller/settings", icon: "⚙️", label: "Store settings", desc: "Delivery radius, store PIN, profile" },
];

export default function QuickActions() {
  return (
    <section className={styles.card}>
      <h2 className={styles.title}>Quick actions</h2>
      <div className={styles.list}>
        {ACTIONS.map((a) => (
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
