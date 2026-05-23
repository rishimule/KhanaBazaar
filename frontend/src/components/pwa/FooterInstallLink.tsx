"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useTranslations } from "next-intl";
import { usePWAInstall } from "./usePWAInstall";
import styles from "./pwa-install.module.css";

export default function FooterInstallLink({ className }: { className?: string }) {
  const t = useTranslations("Footer");
  const { canShowEntry, install } = usePWAInstall();

  if (!canShowEntry) return null;

  return (
    <button
      type="button"
      className={[styles.footerLink, className].filter(Boolean).join(" ")}
      onClick={() => install("footer_link")}
    >
      {t("installApp")}
    </button>
  );
}
