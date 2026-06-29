// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";
import Link from "next/link";
import { useTranslations } from "next-intl";

import styles from "./DeliverabilityFallback.module.css";

/**
 * Fallback banner shown on Home/Stores/Products when a visitor's location is
 * known but nothing is deliverable there. `variant` selects the copy:
 * "stores" (Home + Stores) or "products" (Products). The CTA routes to the
 * seller-onboarding form carrying the source view + current area label.
 */
export default function DeliverabilityFallback({
  variant,
  source,
  areaLabel,
}: {
  variant: "stores" | "products";
  source: string;
  areaLabel?: string;
}) {
  const t = useTranslations("Deliverability");
  const message = variant === "products" ? t("noProducts") : t("noStores");

  return (
    <section className={styles.banner} role="status">
      <span className={styles.icon} aria-hidden="true">
        📍
      </span>
      <p className={styles.message}>{message}</p>
      <Link
        href={{
          pathname: "/suggest-store",
          query: { source, ...(areaLabel ? { area: areaLabel } : {}) },
        }}
        className="btn btn-primary"
      >
        {t("shareSeller")}
      </Link>
    </section>
  );
}
