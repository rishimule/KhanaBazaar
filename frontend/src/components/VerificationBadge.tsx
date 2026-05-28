"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useTranslations } from "next-intl";
import styles from "./VerificationBadge.module.css";

export type VerificationBadgeStatus = "approved" | "pending" | "rejected";

interface Props {
  status: VerificationBadgeStatus;
  reason?: string | null;
}

const GLYPHS: Record<VerificationBadgeStatus, string> = {
  approved: "✓",
  pending: "⏳",
  rejected: "⚠",
};

const VARIANT_CLASS: Record<VerificationBadgeStatus, string> = {
  approved: "badgeApproved",
  pending: "badgePending",
  rejected: "badgeRejected",
};

export default function VerificationBadge({ status, reason }: Props) {
  const t = useTranslations("Shared.verification");
  return (
    <div className={styles.wrap}>
      <span className={`${styles.badge} ${styles[VARIANT_CLASS[status]]}`}>
        <span className={styles.glyph} aria-hidden>
          {GLYPHS[status]}
        </span>
        <span>{t(status)}</span>
      </span>
      {status === "rejected" && reason && (
        <p className={styles.reason}>
          {t("rejectedReason", { reason })}
        </p>
      )}
    </div>
  );
}
