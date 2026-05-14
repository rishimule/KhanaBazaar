"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useLocale } from "next-intl";
import { useTransition } from "react";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { isI18nUnsupported } from "@/i18n/unsupported-routes";
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
  const [pending, startTransition] = useTransition();

  const unsupported = isI18nUnsupported(pathname);
  const disabled = pending || unsupported;

  return (
    <select
      className={`${styles.select} ${unsupported ? styles.disabled : ""}`}
      value={locale}
      disabled={disabled}
      title={unsupported ? "Translation coming soon" : undefined}
      aria-disabled={unsupported}
      aria-label="Change language"
      onChange={(e) => {
        const next = e.target.value;
        startTransition(() => {
          router.replace(pathname, { locale: next });
        });
      }}
    >
      {routing.locales.map((code) => (
        <option key={code} value={code}>
          {LABELS[code]}
        </option>
      ))}
    </select>
  );
}
