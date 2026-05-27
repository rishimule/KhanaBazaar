"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useLocale } from "next-intl";
import { useTransition } from "react";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { localeMode } from "@/i18n/unsupported-routes";
import { useAuth } from "@/lib/AuthContext";
import { persistUserLanguage, setLocaleCookie } from "@/lib/operatorLocale";
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
  const router = useRouter();
  const pathname = usePathname();
  const { token } = useAuth();
  const [pending, startTransition] = useTransition();

  const mode = localeMode(pathname);
  if (mode === "none") return null;

  const onChange = (next: string) => {
    if (mode === "cookie") {
      setLocaleCookie(next);
      void persistUserLanguage(next, token);
      startTransition(() => router.refresh());
    } else {
      startTransition(() => router.replace(pathname, { locale: next }));
    }
  };

  return (
    <select
      className={styles.select}
      value={locale}
      disabled={pending}
      aria-label="Change language"
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
