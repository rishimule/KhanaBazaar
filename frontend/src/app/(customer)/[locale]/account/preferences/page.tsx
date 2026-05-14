"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import { useTranslations } from "next-intl";
import LocaleSwitcher from "@/components/LocaleSwitcher";
import styles from "./page.module.css";

export default function PreferencesPage() {
  const t = useTranslations("Account.preferences");
  return (
    <div className={styles.page}>
      <section className={styles.section}>
        <h2 className={styles.title}>{t("languageTitle")}</h2>
        <p className={styles.subtitle}>{t("languageSubtitle")}</p>
        <LocaleSwitcher />
      </section>
      <section className={styles.section}>
        <h2 className={styles.title}>{t("notificationsTitle")}</h2>
        <p className={styles.empty}>{t("notificationsComingSoon")}</p>
      </section>
    </div>
  );
}
