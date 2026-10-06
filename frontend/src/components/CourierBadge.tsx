"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import styles from "./CourierBadge.module.css";

/** "Ships by courier · few days" — on listing rows that reach the chosen
 *  location only by courier (spec 2026-10-02 §12). Callers decide whether to
 *  render it with `showsCourierBadge`. */
export default function CourierBadge({ className = "" }: { className?: string }) {
  const t = useTranslations("Shared");
  return <span className={`${styles.badge} ${className}`.trim()}>{t("courierBadge")}</span>;
}
