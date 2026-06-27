// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { getTranslations } from "next-intl/server";
import { get } from "@/lib/api";
import PolicyMarkdown from "@/components/PolicyMarkdown";
import styles from "@/components/InfoPage.module.css";

// Render per request so newly-published policy content shows immediately
// (otherwise this page would be frozen at build time via the layout's
// generateStaticParams).
export const dynamic = "force-dynamic";

export default async function TermsPage() {
  const t = await getTranslations("Info");
  let body: string | null = null;
  try {
    const doc = await get<{ body: string }>("/api/v1/policies/terms");
    body = doc.body;
  } catch {
    body = null;
  }
  return (
    <article className={styles.wrap}>
      <h1 className={styles.title}>{t("termsTitle")}</h1>
      {body ? (
        <div className={styles.markdown}>
          <PolicyMarkdown body={body} />
        </div>
      ) : (
        <p className={styles.body}>{t("comingSoon")}</p>
      )}
    </article>
  );
}
