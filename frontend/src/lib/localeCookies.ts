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

/** Cookie owned exclusively by operator (seller/admin) routes. Kept separate
 * from NEXT_LOCALE so next-intl's storefront cookie churn can never flip the
 * dashboard language, and so shopping in another language leaves the dashboard
 * on the operator's saved preference. */
export const OPERATOR_LOCALE_COOKIE = "KB_OP_LOCALE";

/** Locales the app ships (mirror of `routing.locales`). */
export const SUPPORTED_LOCALES = new Set(["en", "hi", "mr", "gu", "pa"]);
export const DEFAULT_LOCALE = "en";

/** Operator (seller/admin) route prefixes — locale lives in KB_OP_LOCALE there.
 * The `(\/|$)` boundary avoids matching e.g. `/sellers` or `/administration`. */
export const OPERATOR_PATH_RE = /^\/(seller|admin)(\/|$)/;

/** Non-default customer locale URL prefixes. With `localePrefix: "as-needed"`
 * the default locale (en) is unprefixed, so only the non-default locales appear
 * as a path segment. This is the authoritative active locale on customer
 * routes. */
export const CUSTOMER_LOCALE_PREFIX_RE = /^\/(hi|mr|gu|pa)(\/|$)/;
