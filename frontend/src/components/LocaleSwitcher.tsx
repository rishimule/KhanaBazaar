"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useLocale, useTranslations } from "next-intl";
import { useTransition } from "react";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { localeMode } from "@/i18n/unsupported-routes";
import { useAuth } from "@/lib/AuthContext";
import { persistUserLanguage, setOperatorLocaleCookie } from "@/lib/operatorLocale";
import styles from "./LocaleSwitcher.module.css";

const LABELS: Record<string, string> = {
  en: "English",
  hi: "हिन्दी",
  mr: "मराठी",
  gu: "ગુજરાતી",
  pa: "ਪੰਜਾਬੀ",
};

export default function LocaleSwitcher() {
  const locale = useLocale();
  const t = useTranslations("Shared");
  const router = useRouter();
  const pathname = usePathname();
  const { token, setPreferredLanguage } = useAuth();
  const [pending, startTransition] = useTransition();

  const mode = localeMode(pathname);
  if (mode === "none") return null;

  const onChange = (next: string) => {
    if (mode === "cookie") {
      // Operator routes: the dashboard locale lives in its own cookie and is
      // baked into the SSR layout. Set the cookie, then hard-reload so the
      // server re-renders in the new locale — router.refresh() does NOT swap a
      // cookie-driven SSR locale. Persist first (await) so the post-reload seed
      // from /auth/me doesn't overwrite the cookie with the stale preference.
      setOperatorLocaleCookie(next);
      void persistUserLanguage(next, token).finally(() => window.location.reload());
    } else {
      // Storefront routes: locale is URL-driven (detection is off). Update the
      // in-memory user so <CustomerLocaleEnforcer> doesn't fight the choice,
      // persist (best-effort), and move the URL to the chosen locale.
      setPreferredLanguage(next);
      void persistUserLanguage(next, token);
      startTransition(() => router.replace(pathname, { locale: next }));
    }
  };

  return (
    <select
      className={styles.select}
      value={locale}
      disabled={pending}
      aria-label={t("localeSwitcher.changeLanguage")}
      onChange={(e) => onChange(e.target.value)}
    >
      {routing.locales.map((code) => (
        <option key={code} value={code}>
          {LABELS[code]}
        </option>
      ))}
    </select>
  );
}
