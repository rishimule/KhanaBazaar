"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import type { Store } from "@/types";
import LanguagePreferenceCard from "@/components/LanguagePreferenceCard";
import styles from "./page.module.css";

export default function SellerSettingsPage() {
  const t = useTranslations("Seller.settings");
  const tc = useTranslations("Seller.common");
  const { token } = useAuth();
  const [store, setStore] = useState<Store | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    get<Store[]>("/api/v1/stores/my", token)
      .then((stores) => {
        if (stores.length > 0) setStore(stores[0]);
      })
      .catch(() => setError(t("loadStoreError")))
      .finally(() => setLoading(false));
  }, [token, t]);

  if (loading) return <div className={styles.empty}>{tc("loading")}</div>;
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

      {error && <div className={styles.errorBanner}>{error}</div>}

      <LanguagePreferenceCard />

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

      <section className={styles.card}>
        <header className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>{t("profileServices")}</h2>
        </header>
        <div className={styles.linkRow}>
          <Link href="/seller/signup?resubmit=true" className="btn btn-outline">
            {t("editProfile")}
          </Link>
          <Link href={`/stores/${store.id}`} className="btn btn-outline">
            {t("viewStorefront")}
          </Link>
        </div>
      </section>
    </div>
  );
}
