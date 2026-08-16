"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import styles from "./error.module.css";

/**
 * Crash net for every operator route (seller + admin).
 *
 * Exists because a stale or duplicate status tap used to white-screen the whole
 * dashboard: the backend returns an object-shaped `detail`, a call site pushed
 * it into render state, React refused to render an object as a child, and
 * nothing caught the throw. Recovery was a manual reload a shop owner has no
 * reason to know about.
 *
 * Next.js renders a segment's error.tsx INSIDE its parent layout, and
 * (operator)/layout.tsx mounts NextIntlClientProvider — so unlike
 * app/global-error.tsx this boundary is fully translatable.
 *
 * Never renders `error.message`: for an ApiError that is the raw backend detail
 * string (or the literal "HTTP 409" when the detail was an object), and showing
 * either to a shop owner is the defect this file exists to stop (audit T2).
 *
 * NOTE: ~20 operator call sites still render `err.message` directly — the rest
 * of T2 is open work, not something this boundary fixes. The rule holds here.
 *
 * A throw inside (operator)/layout.tsx itself is NOT caught here — a segment
 * boundary cannot catch its own layout. That case falls to app/global-error.tsx.
 */
export default function OperatorError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("Errors");
  const pathname = usePathname();
  const home = pathname?.startsWith("/admin") ? "/admin" : "/seller";

  useEffect(() => {
    console.error("[operator] unhandled render error", error);
  }, [error]);

  return (
    <div className={styles.wrap} role="alert">
      <span className={styles.icon} aria-hidden="true">
        ⚠
      </span>
      <h1 className={styles.title}>{t("boundaryTitle")}</h1>
      <p className={styles.body}>{t("boundaryBody")}</p>
      <div className={styles.actions}>
        <button type="button" className={styles.retry} onClick={reset}>
          {t("boundaryRetry")}
        </button>
        <Link href={home} className={styles.home}>
          {t("boundaryHome")}
        </Link>
      </div>
      {error.digest && (
        <p className={styles.ref}>{t("boundaryRef", { digest: error.digest })}</p>
      )}
    </div>
  );
}
