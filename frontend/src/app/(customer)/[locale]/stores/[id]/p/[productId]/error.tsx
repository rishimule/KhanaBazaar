"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import styles from "./ProductFullPage.module.css";

export default function Error() {
  const router = useRouter();
  const t = useTranslations("Product");
  return (
    <main className={styles.page}>
      <p>{t("loadError")}</p>
      <button onClick={() => router.back()}>{t("backToStore")}</button>
    </main>
  );
}
