// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

// Route prefixes where i18n is not yet wired up.
// Middleware strips any locale prefix landing here.
// LocaleSwitcher disables itself on these routes.
// When a prefix gets translated, remove it from this list — both
// middleware and switcher flip behavior together.
export const I18N_UNSUPPORTED_PREFIXES = ["/seller", "/admin", "/dev-logs"] as const;

export function isI18nUnsupported(pathname: string): boolean {
  return I18N_UNSUPPORTED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
}
