"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import styles from "./ProductModal.module.css";

export default function Error() {
  const t = useTranslations("Product");
  const router = useRouter();
  return (
    <div className={styles.backdrop} onClick={() => router.back()}>
      <div className={styles.sheet} onClick={(e) => e.stopPropagation()}>
        <p>{t("loadError")}</p>
        <button onClick={() => router.back()}>{t("backToStore")}</button>
      </div>
    </div>
  );
}
