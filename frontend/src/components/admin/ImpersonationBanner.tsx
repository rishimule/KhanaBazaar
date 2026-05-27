"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import Link from "next/link";
import { useTranslations } from "next-intl";
import styles from "./ImpersonationBanner.module.css";

interface Props {
  businessName: string;
  verificationStatus: string;
  /**
   * "acting" — admin can write here (Products / Orders tabs).
   * "viewing" — read-only context (Activity tab; admin reading its own log).
   */
  variant?: "acting" | "viewing";
}

export default function ImpersonationBanner({
  businessName,
  verificationStatus,
  variant = "acting",
}: Props) {
  const t = useTranslations("Admin.impersonation");
  return (
    <div className={styles.bar} role="status" aria-live="polite">
      <span className={styles.icon} aria-hidden>
        ⚠️
      </span>
      <span className={styles.copy}>
        {variant === "acting"
          ? t.rich("acting", {
              name: businessName,
              strong: (c) => <strong>{c}</strong>,
            })
          : t.rich("viewing", {
              name: businessName,
              strong: (c) => <strong>{c}</strong>,
            })}
      </span>
      <span className={styles.status}>{verificationStatus}</span>
      <Link href="/admin/sellers" className={styles.exit}>
        {t("exit")}
      </Link>
    </div>
  );
}
