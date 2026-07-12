"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useRef } from "react";
import { useLocale } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing, type AppLocale } from "@/i18n/routing";
import { useAuth } from "@/lib/AuthContext";
import { setLocaleCookie } from "@/lib/operatorLocale";

/**
 * Makes a logged-in customer's saved language preference authoritative for the
 * storefront. Customer locale is URL-driven, and `localePrefix: "as-needed"`
 * lets browser Accept-Language redirect an unprefixed visit to a non-default
 * locale — so a customer who prefers English on a Hindi-language device would
 * otherwise keep landing in Hindi. This reconciles the URL to the persisted
 * `User.preferred_language` after auth resolves.
 *
 * The cookie is pinned *before* navigating so next-intl's middleware doesn't
 * bounce the redirect straight back via Accept-Language. Renders nothing.
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
    setLocaleCookie(pref);
    router.replace(pathname, { locale: pref });
  }, [loading, pref, locale, pathname, router]);

  return null;
}
