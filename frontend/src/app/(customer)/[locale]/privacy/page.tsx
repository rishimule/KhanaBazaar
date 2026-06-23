// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { getTranslations } from "next-intl/server";
import styles from "@/components/InfoPage.module.css";

export default async function PrivacyPage() {
  const t = await getTranslations("Info");
  return (
    <article className={styles.wrap}>
      <h1 className={styles.title}>{t("privacyTitle")}</h1>
      <p className={styles.body}>{t("comingSoon")}</p>
    </article>
  );
}
