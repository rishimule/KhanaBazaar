// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useTranslations } from "next-intl";

import styles from "./CrownBadge.module.css";

const CrownSvg = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M3 7l4.5 3.5L12 4l4.5 6.5L21 7l-1.6 11H4.6L3 7z" />
  </svg>
);

interface Props {
  variant?: "icon" | "pill";
  className?: string;
}

/**
 * Premium indicator for stores that carry a live paid (non-Freebie) fee
 * arrangement. Callers gate rendering themselves: `{store.is_premium && <CrownBadge />}`.
 */
export default function CrownBadge({ variant = "icon", className = "" }: Props) {
  const t = useTranslations("Shared");

  if (variant === "pill") {
    return (
      <span
        className={`badge badge--premium ${className}`.trim()}
        aria-label={t("premiumBadgeAria")}
      >
        <CrownSvg />
        {t("premiumBadge")}
      </span>
    );
  }

  return (
    <span
      className={`${styles.icon} ${className}`.trim()}
      role="img"
      aria-label={t("premiumBadgeAria")}
      title={t("premiumBadgeAria")}
    >
      <CrownSvg />
    </span>
  );
}
