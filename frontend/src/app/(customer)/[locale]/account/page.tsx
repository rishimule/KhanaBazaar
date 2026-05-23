"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AccountInstallShortcut from "@/components/pwa/AccountInstallShortcut";
import ActiveOrdersWidget from "@/components/orders/ActiveOrdersWidget";
import RecentlyViewedRail from "@/components/RecentlyViewedRail";
import StatsCard from "@/components/StatsCard";
import { get } from "@/lib/api";
import { getCustomerStats } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import { useFavorites } from "@/lib/FavoritesContext";
import type { CustomerProfile, CustomerStats } from "@/types";
import styles from "./page.module.css";

const SHORTCUTS = [
  { href: "/account/orders", icon: "📦", labelKey: "shortcutOrders" },
  { href: "/account/favorites", icon: "❤️", labelKey: "shortcutFavorites" },
  { href: "/account/addresses", icon: "📍", labelKey: "shortcutAddresses" },
  { href: "/account/support", icon: "💬", labelKey: "shortcutSupport" },
] as const;

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

  const initial = (firstName || "?").charAt(0).toUpperCase();
  const orderCount = stats?.orders_this_month ?? 0;
  const lifetime = stats?.lifetime_spend ?? 0;

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroDecor} aria-hidden="true" />
        <div className={styles.heroInner}>
          <div className={styles.avatar} aria-hidden="true">
            {initial}
          </div>
          <div className={styles.heroText}>
            <span className={styles.heroEyebrow} suppressHydrationWarning>
              {today}
            </span>
            <h1 className={styles.heroTitle}>
              {t("greeting", { name: firstName || t("there") })}
            </h1>
            <p className={styles.heroBlurb}>
              {t("heroBlurb", { count: orderCount })}
              {lifetime > 0 && (
                <>
                  <span className={styles.heroDot} aria-hidden="true">·</span>
                  {t("heroBlurbSpend", { amount: lifetime.toFixed(0) })}
                </>
              )}
            </p>
          </div>
        </div>
      </section>

      <section className={styles.shortcuts} aria-label={t("quickActions")}>
        {SHORTCUTS.map((s) => (
          <Link key={s.href} href={s.href} className={styles.shortcut}>
            <span className={styles.shortcutIcon} aria-hidden="true">
              {s.icon}
            </span>
            <span className={styles.shortcutLabel}>{t(s.labelKey)}</span>
          </Link>
        ))}
        <AccountInstallShortcut
          shortcutClassName={styles.shortcut}
          iconClassName={styles.shortcutIcon}
          labelClassName={styles.shortcutLabel}
        />
      </section>

      <section className={styles.activeBlock}>
        <ActiveOrdersWidget role="customer" limit={5} />
      </section>

      {stats && (
        <section className={styles.statsStrip}>
          <StatsCard
            icon="📦"
            label={t("ordersThisMonth")}
            value={String(stats.orders_this_month)}
            variant="primary"
          />
          <StatsCard
            icon="💸"
            label={t("lifetimeSpend")}
            value={`₹${stats.lifetime_spend.toFixed(0)}`}
            variant="accent"
          />
          <StatsCard
            icon="⭐"
            label={t("mostOrderedStore")}
            value={stats.most_ordered_store_name ?? "—"}
            variant="warning"
          />
          <Link href={`/${locale}/account/favorites`} className={styles.statLink}>
            <StatsCard
              icon="❤️"
              label={t("favouritesCount")}
              value={String(favCount)}
              variant="info"
            />
          </Link>
        </section>
      )}

      {stats && stats.recent_delivered.length > 0 && (
        <section className={styles.rail}>
          <header className={styles.railHead}>
            <h2 className={styles.railTitle}>{t("orderAgain")}</h2>
            <Link href={`/${locale}/account/orders`} className={styles.railLink}>
              {t("viewAll")}
            </Link>
          </header>
          <div className={styles.railList}>
            {stats.recent_delivered.map((o) => (
              <Link
                key={o.id}
                href={`/account/orders/${o.id}`}
                className={styles.railCard}
              >
                <div className={styles.railThumb} aria-hidden="true">
                  {o.store_name.charAt(0).toUpperCase()}
                </div>
                <div className={styles.railBody}>
                  <span className={styles.railStore}>{o.store_name}</span>
                  <span className={styles.railService}>{o.service_name}</span>
                  <span className={styles.railMeta} suppressHydrationWarning>
                    {new Date(o.placed_at).toLocaleDateString()} · ₹{o.total.toFixed(0)}
                  </span>
                </div>
                <span className={styles.railCta} aria-hidden="true">
                  {t("reorderCta")} →
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      <div className={styles.recentlyBlock}>
        <RecentlyViewedRail />
      </div>
    </div>
  );
}
