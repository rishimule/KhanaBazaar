"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import styles from "./CourierBadge.module.css";

/** "Ships by courier · few days" — on listing rows that reach the chosen
 *  location only by courier (spec 2026-10-02 §12). Callers decide whether to
 *  render it with `showsCourierBadge`.
 *  - `start`: inside a column flexbox, keep the pill its own width;
 *  - `wrap`: on narrow rows, let the label wrap instead of widening the row. */
export default function CourierBadge({
  className = "",
  start = false,
  wrap = false,
}: {
  className?: string;
  start?: boolean;
  wrap?: boolean;
}) {
  const t = useTranslations("Shared");
  const classes = [styles.badge, start && styles.start, wrap && styles.wrap, className]
    .filter(Boolean)
    .join(" ");
  return <span className={classes}>{t("courierBadge")}</span>;
}
