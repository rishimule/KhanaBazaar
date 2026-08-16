// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useTranslations } from "next-intl";

import { errorsKey } from "@/lib/errors";
import styles from "./LoadError.module.css";

export type LoadErrorVariant = "card" | "inline" | "banner";

interface LoadErrorProps {
  /** The caught error. Used only to pick a translated message — never rendered raw. */
  error?: unknown;
  /** Retry handler. When omitted, no retry affordance is shown. */
  onRetry?: () => void;
  variant?: LoadErrorVariant;
  /** Surface-specific heading, e.g. "Couldn't load your orders". */
  title?: string;
  /** Surface-specific explanation. Falls back to the mapped error, then generic copy. */
  body?: string;
  retryLabel?: string;
  className?: string;
}

/**
 * The one degraded-state component for the seller surface.
 *
 * Exists because a swallowed fetch error used to render as "₹0", "No orders
 * match these filters" or an absent warning — states a shop owner reads as the
 * truth about their business. Rendering this instead is the difference between
 * "I earned nothing" and "the app could not load".
 *
 * Render-safe by construction: it never prints a raw backend `detail` (which
 * can be an object for structured FastAPI errors, and would crash the render).
 * It resolves to a translated `Errors.*` string or to the caller's own copy.
 */
export default function LoadError({
  error,
  onRetry,
  variant = "card",
  title,
  body,
  retryLabel,
  className,
}: LoadErrorProps) {
  const t = useTranslations("Seller.common");
  const tErr = useTranslations("Errors");

  const mappedKey = errorsKey(error);
  const mapped = mappedKey ? tErr(mappedKey) : null;

  const heading = title ?? t("loadFailedTitle");
  const explanation = body ?? mapped ?? t("loadFailedBody");

  const rootClass = [styles.root, styles[variant], className]
    .filter(Boolean)
    .join(" ");

  const retry = onRetry ? (
    <button type="button" className={styles.retry} onClick={onRetry}>
      {retryLabel ?? t("retry")}
    </button>
  ) : null;

  if (variant === "card") {
    return (
      <div className={rootClass} role="alert">
        <span className={styles.icon} aria-hidden="true">
          ⚠
        </span>
        <p className={styles.title}>{heading}</p>
        <p className={styles.body}>{explanation}</p>
        {retry}
      </div>
    );
  }

  return (
    <div className={rootClass} role="alert">
      <span className={styles.icon} aria-hidden="true">
        ⚠
      </span>
      <span className={styles.text}>{heading}</span>
      {retry}
    </div>
  );
}
