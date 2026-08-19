"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import type { Store } from "@/types";
import LanguagePreferenceCard from "@/components/LanguagePreferenceCard";
import ReturnWindowCard from "@/components/returns/ReturnWindowCard";
import LoadError from "@/components/LoadError";
import styles from "./page.module.css";

export default function SellerSettingsPage() {
  const t = useTranslations("Seller.settings");
  const tc = useTranslations("Seller.common");
  const { token } = useAuth();
  const { data: stores, loading, error, refetch } = useResource<Store[]>(
    token ? () => get<Store[]>("/api/v1/stores/my", token) : null,
    [Boolean(token)],
  );
  const store = stores?.[0] ?? null;

  if (loading) return <div className={styles.empty}>{tc("loading")}</div>;
  // `error` must be checked BEFORE `!store`: the old order returned the
  // "No store" empty state first, which made the error banner structurally
  // unreachable and blamed the seller's setup for a network fault.
  if (error) {
    return (
      <div className={styles.page}>
        <LoadError
          variant="card"
          error={error}
          title={t("loadStoreError")}
          onRetry={() => refetch()}
        />
      </div>
    );
  }
  if (!store) return <div className={styles.empty}>{t("noStore")}</div>;

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{t("title")}</h1>

      {!store.pin_confirmed && (
        <div className={styles.pinBanner}>
          {t.rich("pinBanner", { strong: (chunks) => <strong>{chunks}</strong> })}{" "}
          <Link href="/seller/signup?resubmit=true" className={styles.bannerLink}>
            {t("dropPin")}
          </Link>
        </div>
      )}


      <LanguagePreferenceCard />

      <ReturnWindowCard />

      <section className={styles.card}>
        <header className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>{t("storeDetails")}</h2>
        </header>
        <dl className={styles.detailGrid}>
          <dt>{t("storeName")}</dt>
          <dd>{store.name}</dd>
          <dt>{t("status")}</dt>
          <dd>{store.is_active ? t("active") : t("inactive")}</dd>
          <dt>{t("pinConfirmed")}</dt>
          <dd>{store.pin_confirmed ? t("yes") : t("no")}</dd>
        </dl>
      </section>
    </div>
  );
}
