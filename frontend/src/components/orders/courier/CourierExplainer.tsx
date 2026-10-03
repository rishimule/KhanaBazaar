"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useTranslations } from "next-intl";
import styles from "./courier.module.css";

/** The long-distance explainer shown the moment a courier address is picked
 *  (spec §8.2) — so nobody places a courier order thinking it's local. */
export default function CourierExplainer({
  storeName,
  city,
}: {
  storeName: string;
  city: string | null;
}) {
  const t = useTranslations("Checkout.courier");
  return (
    <section className={styles.explainer} aria-labelledby="courier-explainer-title">
      <h2 id="courier-explainer-title" className={styles.title}>
        <span aria-hidden="true">📦 </span>
        {t("title")}
      </h2>
      <p className={styles.body}>
        {city ? t("bodyCity", { city, store: storeName }) : t("body", { store: storeName })}
      </p>
      <ul className={styles.points}>
        <li>{t("pointCharge", { store: storeName })}</li>
        <li>{t("pointPayLater")}</li>
        <li>{t("pointNoReturns")}</li>
      </ul>
    </section>
  );
}
