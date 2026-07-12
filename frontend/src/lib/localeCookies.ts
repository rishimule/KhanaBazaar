// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

/**
 * Shared locale constants. This module intentionally has NO runtime imports so
 * it can be imported from `api.ts`, `operatorLocale.ts`, and `AuthContext.tsx`
 * without any circular-dependency risk (operatorLocale imports `patch` from
 * api.ts). Keep the locale list in sync with `@/i18n/routing`.
 */

/** Cookie owned by next-intl for customer (storefront) routes. We also write it
 * on an explicit customer language choice so the pick survives Accept-Language
 * detection (next-intl ranks the cookie above the browser header). */
export const CUSTOMER_LOCALE_COOKIE = "NEXT_LOCALE";

/** Cookie carrying the operator (seller/admin) dashboard locale.
 *
 * It is named `__session` on purpose: the prod web domain is Firebase Hosting →
 * Cloud Run, and Firebase strips EVERY request cookie except `__session` before
 * it reaches the origin. Operator routes are non-localized (no URL locale), so
 * their SSR layout must read the locale from a cookie — and `__session` is the
 * only cookie that survives to the origin on prod. (The storefront doesn't need
 * this: its locale is URL-driven.)
 *
 * The value is a bare locale code (e.g. "hi"); readers validate it against
 * `routing.locales` and fall back to the default, so if `__session` is ever
 * repurposed for other session data this degrades gracefully to English rather
 * than breaking. `__session` is set with path=/, so a dual-role operator who
 * also shops sends it on storefront requests too — harmless (storefront never
 * reads it; it only becomes part of Firebase's cache key, and storefront HTML
 * is already no-cache). */
export const OPERATOR_LOCALE_COOKIE = "__session";

/** Locales the app ships (mirror of `routing.locales`). */
export const SUPPORTED_LOCALES = new Set(["en", "hi", "mr", "gu", "pa"]);
export const DEFAULT_LOCALE = "en";

/** Operator (seller/admin) route prefixes — locale lives in OPERATOR_LOCALE_COOKIE
 * there. The `(\/|$)` boundary avoids matching e.g. `/sellers` or `/administration`. */
export const OPERATOR_PATH_RE = /^\/(seller|admin)(\/|$)/;

/** Non-default customer locale URL prefixes. With `localePrefix: "as-needed"`
 * the default locale (en) is unprefixed, so only the non-default locales appear
 * as a path segment. This is the authoritative active locale on customer
 * routes. */
export const CUSTOMER_LOCALE_PREFIX_RE = /^\/(hi|mr|gu|pa)(\/|$)/;
