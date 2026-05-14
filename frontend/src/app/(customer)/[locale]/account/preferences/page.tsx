"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { get, patch } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import LocaleSwitcher from "@/components/LocaleSwitcher";
import type { CustomerProfile } from "@/types";
import styles from "./page.module.css";

const LANGS = ["en", "hi", "mr", "gu", "pa"] as const;

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

  if (!profile) {
    return (
      <div className={styles.page}>
        <p className={styles.empty}>{error ?? t("loading")}</p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <section className={styles.section}>
        <h2 className={styles.title}>{t("languageTitle")}</h2>
        <p className={styles.subtitle}>{t("languageSubtitle")}</p>
        <select
          className={styles.select}
          value={profile.preferred_language ?? ""}
          onChange={(e) =>
            save({ preferred_language: e.target.value || null })
          }
          disabled={busy}
        >
          <option value="">{t("languageDefault")}</option>
          {LANGS.map((l) => (
            <option key={l} value={l}>
              {t(`lang.${l}`)}
            </option>
          ))}
        </select>
        <div style={{ marginTop: 16 }}>
          <LocaleSwitcher />
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.title}>{t("notificationsTitle")}</h2>
        <div className={styles.toggleList}>
          <label className={styles.toggleRow}>
            <input
              type="checkbox"
              checked={profile.notify_order_email}
              onChange={(e) =>
                save({ notify_order_email: e.target.checked })
              }
              disabled={busy}
            />
            {t("notifyOrderEmail")}
          </label>
          <label className={styles.toggleRow}>
            <input
              type="checkbox"
              checked={profile.notify_order_sms}
              onChange={(e) =>
                save({ notify_order_sms: e.target.checked })
              }
              disabled={busy}
            />
            {t("notifyOrderSms")}
          </label>
          <label className={styles.toggleRow}>
            <input
              type="checkbox"
              checked={profile.marketing_opt_in}
              onChange={(e) =>
                save({ marketing_opt_in: e.target.checked })
              }
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
