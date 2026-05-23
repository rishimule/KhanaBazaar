"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import ActiveOrdersWidget from "@/components/orders/ActiveOrdersWidget";
import RecentlyViewedRail from "@/components/RecentlyViewedRail";
import StatsCard from "@/components/StatsCard";
import { get } from "@/lib/api";
import { getCustomerStats } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import { useFavorites } from "@/lib/FavoritesContext";
import type { CustomerProfile, CustomerStats } from "@/types";
import styles from "./page.module.css";

export default function AccountHomePage() {
  const t = useTranslations("Account.dashboard");
  const locale = useLocale();
  const { token } = useAuth();
  const { count: favCount } = useFavorites();
  const [stats, setStats] = useState<CustomerStats | null>(null);
  const [firstName, setFirstName] = useState<string>("");

  useEffect(() => {
    if (!token) return;
    getCustomerStats(token)
      .then(setStats)
      .catch(() => setStats(null));
    get<CustomerProfile>("/api/v1/customers/me", token)
      .then((p) => setFirstName(p.first_name))
      .catch(() => {});
  }, [token]);

  const today = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <div className={styles.page}>
      <section className={`${styles.greet} ${styles.full}`}>
        <h1 className={styles.greetTitle}>
          {t("greeting", { name: firstName || t("there") })} 👋
        </h1>
        <p className={styles.greetSub} suppressHydrationWarning>
          {today}
        </p>
      </section>

      <section className={styles.full}>
        <ActiveOrdersWidget role="customer" limit={5} />
      </section>

      {stats && (
        <section className={`${styles.statsStrip} ${styles.full}`}>
          <StatsCard icon="📦" label={t("ordersThisMonth")} value={String(stats.orders_this_month)} />
          <StatsCard
            icon="💸"
            label={t("lifetimeSpend")}
            value={`₹${stats.lifetime_spend.toFixed(0)}`}
          />
          <StatsCard
            icon="⭐"
            label={t("mostOrderedStore")}
            value={stats.most_ordered_store_name ?? "—"}
          />
          <Link href={`/${locale}/account/favorites`} className={styles.statLink}>
            <StatsCard
              icon="❤️"
              label={t("favouritesCount")}
              value={String(favCount)}
            />
          </Link>
        </section>
      )}

      {stats && stats.recent_delivered.length > 0 && (
        <section className={`${styles.rail} ${styles.full}`}>
          <h2 className={styles.railTitle}>{t("orderAgain")}</h2>
          <div className={styles.railList}>
            {stats.recent_delivered.map((o) => (
              <Link
                key={o.id}
                href={`/account/orders/${o.id}`}
                className={styles.railCard}
              >
                <span className={styles.railStore}>{o.store_name}</span>
                <span className={styles.railMeta}>
                  {o.service_name} · ₹{o.total.toFixed(0)}
                </span>
                <span className={styles.railMeta} suppressHydrationWarning>
                  {new Date(o.placed_at).toLocaleDateString()}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      <div className={styles.full}>
        <RecentlyViewedRail />
      </div>
    </div>
  );
}
