"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import { Store } from "@/types";
import styles from "./page.module.css";

export default function StoresPage() {
  const t = useTranslations("Stores");
  const [stores, setStores] = useState<Store[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    get<Store[]>("/api/v1/stores/")
      .then(setStores)
      .catch(() => setStores([]))
      .finally(() => setFetching(false));
  }, []);

  if (fetching) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <div className={styles.header}>
            <h1 className={styles.title}>{t("loading")}</h1>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        <div className={styles.header}>
          <h1 className={styles.title}>
            {t("browse")} <span className={styles.titleAccent}>{t("stores")}</span>
          </h1>
          <p className={styles.subtitle}>{t("subtitle")}</p>
        </div>

        <div className={styles.grid}>
          {stores.map((store) => (
            <Link
              key={store.id}
              href={`/stores/${store.id}`}
              className={styles.card}
              id={`store-card-${store.id}`}
            >
              <div className={styles.cardIcon}>🏪</div>
              <h2 className={styles.cardName}>{store.name}</h2>
              <p className={styles.cardAddress}>{formatAddress(store.address)}</p>
              <div className={styles.cardMeta}>
                <span className={styles.cardStatus}>{t("openDot")}</span>
              </div>
              <span className={styles.viewBtn}>{t("viewStore")}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
