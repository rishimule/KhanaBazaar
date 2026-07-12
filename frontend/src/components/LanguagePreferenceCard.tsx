"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { routing } from "@/i18n/routing";
import { useAuth } from "@/lib/AuthContext";
import { persistUserLanguage, setOperatorLocaleCookie } from "@/lib/operatorLocale";
import styles from "./LanguagePreferenceCard.module.css";

const LABELS: Record<string, string> = {
  en: "English",
  hi: "हिन्दी",
  mr: "मराठी",
  gu: "ગુજરાતી",
  pa: "ਪੰਜਾਬੀ",
};

export default function LanguagePreferenceCard() {
  const t = useTranslations("Shared.languagePreference");
  const locale = useLocale();
  const { token } = useAuth();
  const [pending, setPending] = useState(false);

  const onChange = (next: string) => {
    // This card only renders on operator (seller/admin) settings pages, where
    // the locale lives in the operator cookie and is baked into the SSR layout.
    // Set the cookie, then hard-reload so the server re-renders in the new
    // locale — router.refresh() does NOT swap a cookie-driven SSR locale.
    // Persist first (await) so the post-reload seed from /auth/me doesn't
    // overwrite the cookie with the stale preference.
    setPending(true);
    setOperatorLocaleCookie(next);
    void persistUserLanguage(next, token).finally(() => window.location.reload());
  };

  return (
    <section className={styles.card}>
      <header className={styles.cardHeader}>
        <h2 className={styles.cardTitle}>{t("title")}</h2>
        <p className={styles.cardCaption}>{t("caption")}</p>
      </header>
      <div className={styles.row}>
        <select
          className={styles.select}
          value={locale}
          disabled={pending}
          aria-label={t("ariaLabel")}
          onChange={(e) => onChange(e.target.value)}
        >
          {routing.locales.map((code) => (
            <option key={code} value={code}>
              {LABELS[code] ?? code}
            </option>
          ))}
        </select>
        {pending && (
          <span className={styles.savingChip} aria-live="polite">
            {t("saving")}
          </span>
        )}
      </div>
    </section>
  );
}
