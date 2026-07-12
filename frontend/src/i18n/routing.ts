// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en", "hi", "mr", "gu", "pa"] as const,
  defaultLocale: "en",
  localePrefix: "as-needed",
  // Locale is URL-driven, not auto-detected from the browser. Two reasons:
  // (1) it respects an explicit English preference — Accept-Language detection
  // was redirecting unprefixed `/` to `/hi` for regional-language browsers,
  // overriding users who want English; (2) it works on the prod domain, where
  // Firebase Hosting strips every cookie except `__session` before proxying to
  // Cloud Run, so cookie-based locale detection never reaches the origin.
  // Default is English (unprefixed); users opt into other locales via the
  // switcher (URL prefix), and a logged-in customer's saved preference is
  // applied by <CustomerLocaleEnforcer>.
  localeDetection: false,
});

export type AppLocale = (typeof routing.locales)[number];
