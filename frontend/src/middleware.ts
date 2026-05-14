// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import createMiddleware from "next-intl/middleware";
import { NextRequest, NextResponse } from "next/server";
import { routing } from "./i18n/routing";
import { isI18nUnsupported } from "./i18n/unsupported-routes";

const intlMiddleware = createMiddleware(routing);

// Non-default locales only. With localePrefix: "as-needed",
// the default locale ("en") is unprefixed and never appears here.
const LOCALE_PREFIX_RE = /^\/(hi|mr|gu|pa)(\/.*)?$/;

export default function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const match = pathname.match(LOCALE_PREFIX_RE);

  if (match) {
    // Strip trailing slash so we canonicalize "/hi/seller/" -> "/seller".
    // next.config.ts has skipTrailingSlashRedirect: true, so Next will not
    // normalize this for us.
    const stripped = (match[2] ?? "/").replace(/\/+$/, "") || "/";
    if (isI18nUnsupported(stripped)) {
      // Build a fresh URL: NextURL.clone() + pathname setter leaves a
      // stale trailing slash in .href even after updating pathname.
      const target = new URL(stripped + req.nextUrl.search, req.url);
      // 308 preserves method + body per RFC 7538.
      return NextResponse.redirect(target, 308);
    }
  }

  // Unprefixed operator / dev-logs paths: skip next-intl entirely so
  // it does not read or write the NEXT_LOCALE cookie on those routes.
  if (isI18nUnsupported(pathname)) {
    return NextResponse.next();
  }

  return intlMiddleware(req);
}

export const config = {
  matcher: [
    "/((?!api|_next|favicon\\.ico|icons|manifest\\.json|sw\\.js|.*\\.(?:png|jpg|jpeg|svg|webp|ico)).*)",
  ],
};
