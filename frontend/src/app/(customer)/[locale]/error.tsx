"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

import styles from "./error.module.css";

/**
 * Crash net for the customer storefront.
 *
 * Sibling of (operator)/error.tsx, added for the same reason: several customer
 * call sites pushed a possibly-object `ApiError.detail` into render state, and
 * React refuses an object as a child. Until now the storefront had NO boundary
 * at all — only two product-detail ones — so any such throw fell through to
 * app/global-error.tsx, which replaces the whole document with English-only
 * copy. That is the worst possible outcome for the one audience that is
 * genuinely multilingual.
 *
 * Placed at [locale] so it renders inside that layout's NextIntlClientProvider
 * and is therefore translated in all five locales. Uses the localized <Link>
 * from @/i18n/navigation so "keep shopping" stays on the visitor's locale.
 *
 * Never renders `error.message`: for an ApiError that is the raw backend detail
 * (or the literal "HTTP 409" when the detail was an object).
 */
export default function CustomerError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("Errors");

  useEffect(() => {
    console.error("[storefront] unhandled render error", error);
  }, [error]);

  return (
    <div className={styles.wrap} role="alert">
      <span className={styles.icon} aria-hidden="true">
        ⚠
      </span>
      <h1 className={styles.title}>{t("boundaryTitle")}</h1>
      {/* Shop-specific body: the shared boundaryBody says "back to your
          dashboard", which means nothing to a shopper. */}
      <p className={styles.body}>{t("boundaryBodyShop")}</p>
      <div className={styles.actions}>
        <button type="button" className={styles.retry} onClick={reset}>
          {t("boundaryRetry")}
        </button>
        <Link href="/" className={styles.home}>
          {t("boundaryShopHome")}
        </Link>
      </div>
      {error.digest && (
        <p className={styles.ref}>{t("boundaryRef", { digest: error.digest })}</p>
      )}
    </div>
  );
}
