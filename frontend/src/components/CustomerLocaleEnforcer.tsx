"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useRef } from "react";
import { useLocale } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing, type AppLocale } from "@/i18n/routing";
import { useAuth } from "@/lib/AuthContext";

/**
 * Makes a logged-in customer's saved language preference authoritative for the
 * storefront by reconciling the URL locale to `User.preferred_language` after
 * auth resolves. Customer locale is URL-driven (locale detection is off, so the
 * URL is the source of truth), which is why moving the URL is sufficient and
 * works on the prod domain (no cookie needed at the origin). Renders nothing.
 */
export default function CustomerLocaleEnforcer() {
  const { dbUser, loading } = useAuth();
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  // Target we last redirected toward, so we don't re-fire while the (async)
  // navigation is still settling the URL locale.
  const lastTargetRef = useRef<string | null>(null);

  const pref = dbUser?.preferred_language ?? null;

  useEffect(() => {
    if (loading || !pref) return;
    if (!routing.locales.includes(pref as AppLocale)) return;
    if (pref === locale) {
      lastTargetRef.current = null;
      return;
    }
    if (lastTargetRef.current === pref) return;
    lastTargetRef.current = pref;
    router.replace(pathname, { locale: pref });
  }, [loading, pref, locale, pathname, router]);

  return null;
}
