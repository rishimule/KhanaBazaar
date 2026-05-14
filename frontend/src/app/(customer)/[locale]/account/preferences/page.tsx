"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import { useEffect, useState, useTransition } from "react";
import { useLocale, useTranslations } from "next-intl";
import { get, patch } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { usePathname, useRouter } from "@/i18n/navigation";
import type { CustomerProfile } from "@/types";
import styles from "./page.module.css";

const LANGS = ["en", "hi", "mr", "gu", "pa"] as const;
type Lang = (typeof LANGS)[number];

const LANG_LABELS: Record<Lang, string> = {
  en: "English",
  hi: "हिन्दी (Hindi)",
  mr: "मराठी (Marathi)",
  gu: "ગુજરાતી (Gujarati)",
  pa: "ਪੰਜਾਬੀ (Punjabi)",
};

type PreferencesPatch = Partial<
  Pick<
    CustomerProfile,
    | "preferred_language"
    | "marketing_opt_in"
    | "notify_order_email"
    | "notify_order_sms"
  >
>;

export default function PreferencesPage() {
  const t = useTranslations("Account.preferences");
  const { token } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const locale = useLocale();
  const [, startTransition] = useTransition();
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    get<CustomerProfile>("/api/v1/customers/me", token)
      .then(setProfile)
      .catch(() => setError(t("loadError")));
  }, [token, t]);

  const save = async (patchBody: PreferencesPatch) => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const next = await patch<CustomerProfile>(
        "/api/v1/customers/me/preferences",
        patchBody,
        token,
      );
      setProfile(next);
    } catch {
      setError(t("saveError"));
    } finally {
      setBusy(false);
    }
  };

  const onLanguageChange = async (value: string) => {
    const next = (value || null) as Lang | null;
    await save({ preferred_language: next });
    if (next && next !== locale) {
      startTransition(() => {
        router.replace(pathname, { locale: next });
      });
    }
  };

  if (!profile) {
    return (
      <div className={styles.page}>
        <p className={styles.empty}>{error ?? t("loading")}</p>
      </div>
    );
  }

  // The "active" language is the saved server preference; if absent, fall
  // back to the URL locale (matches what the user sees right now).
  const activeLang = profile.preferred_language ?? locale;

  return (
    <div className={styles.page}>
      <section className={styles.section}>
        <h2 className={styles.title}>{t("languageTitle")}</h2>
        <p className={styles.subtitle}>{t("languageSubtitle")}</p>
        <select
          className={styles.select}
          value={activeLang}
          onChange={(e) => onLanguageChange(e.target.value)}
          disabled={busy}
          aria-label={t("languageTitle")}
        >
          {LANGS.map((l) => (
            <option key={l} value={l}>
              {LANG_LABELS[l]}
            </option>
          ))}
        </select>
      </section>

      <section className={styles.section}>
        <h2 className={styles.title}>{t("notificationsTitle")}</h2>
        <div className={styles.toggleList}>
          <label className={styles.toggleRow}>
            <input
              type="checkbox"
              checked={profile.notify_order_email}
              onChange={(e) => save({ notify_order_email: e.target.checked })}
              disabled={busy}
            />
            {t("notifyOrderEmail")}
          </label>
          <label className={styles.toggleRow}>
            <input
              type="checkbox"
              checked={profile.notify_order_sms}
              onChange={(e) => save({ notify_order_sms: e.target.checked })}
              disabled={busy}
            />
            {t("notifyOrderSms")}
          </label>
          <label className={styles.toggleRow}>
            <input
              type="checkbox"
              checked={profile.marketing_opt_in}
              onChange={(e) => save({ marketing_opt_in: e.target.checked })}
              disabled={busy}
            />
            {t("marketingOptIn")}
          </label>
        </div>
        {error && <p className={styles.empty}>{error}</p>}
      </section>
    </div>
  );
}
