// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

// Route prefixes that do NOT carry a locale URL prefix.
// Middleware uses this list to bypass next-intl URL routing and to strip any
// locale prefix that lands here (e.g. /hi/seller -> /seller).
export const I18N_UNSUPPORTED_PREFIXES = [
  "/seller",
  "/admin",
  "/dev-logs",
  "/dev-emails",
  "/dev-sms",
] as const;

export function isI18nUnsupported(pathname: string): boolean {
  return I18N_UNSUPPORTED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
}

export type LocaleMode = "url" | "cookie" | "none";

// INVARIANT: COOKIE_LOCALE_PREFIXES ∪ NO_LOCALE_PREFIXES must equal
// I18N_UNSUPPORTED_PREFIXES above (middleware bypasses next-intl URL routing
// for that whole list). If you add an operator prefix, add it to BOTH or the
// switcher and middleware will silently disagree.
// "none" = routes that are not React pages (dev-logs proxy) — no switcher.
const COOKIE_LOCALE_PREFIXES = ["/seller", "/admin"] as const;
const NO_LOCALE_PREFIXES = ["/dev-logs", "/dev-emails", "/dev-sms"] as const;

/** How the LocaleSwitcher should behave on a given path.
 * - "url"    : customer routes — locale lives in the URL prefix.
 * - "cookie" : operator routes — locale lives in the NEXT_LOCALE cookie.
 * - "none"   : non-page routes — switcher renders nothing.
 */
export function localeMode(pathname: string): LocaleMode {
  const hits = (prefixes: readonly string[]) =>
    prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  if (hits(NO_LOCALE_PREFIXES)) return "none";
  if (hits(COOKIE_LOCALE_PREFIXES)) return "cookie";
  return "url";
}
