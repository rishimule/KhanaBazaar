// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import createMiddleware from "next-intl/middleware";
import { NextRequest, NextResponse } from "next/server";
import { routing } from "./i18n/routing";
import { isI18nUnsupported } from "./i18n/unsupported-routes";

const intlMiddleware = createMiddleware(routing);

// Behind Cloud Run, the Next server listens on :8080 and next-intl builds
// absolute redirect URLs (e.g. the default-locale "/en/x" -> "/x" strip) whose
// Location header leaks ":8080". The public origin is always HTTPS:443, so a
// ":8080" URL is unreachable from the browser. Strip any port from the redirect
// Location. No-op for relative Locations and for the standard :443.
function sanitizeRedirectPort<T extends Response>(res: T): T {
  const loc = res.headers.get("location");
  if (loc) {
    try {
      const u = new URL(loc);
      if (u.port) {
        u.port = "";
        res.headers.set("location", u.toString());
      }
    } catch {
      // Relative Location — nothing to sanitize.
    }
  }
  return res;
}

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
      return sanitizeRedirectPort(NextResponse.redirect(target, 308));
    }
  }

  // Unprefixed operator / dev-logs paths: skip next-intl entirely so
  // it does not read or write the NEXT_LOCALE cookie on those routes.
  if (isI18nUnsupported(pathname)) {
    return NextResponse.next();
  }

  return sanitizeRedirectPort(intlMiddleware(req) as NextResponse);
}

export const config = {
  matcher: [
    "/((?!api|_next|favicon\\.ico|icons|manifest\\.json|sw\\.js|.*\\.(?:png|jpg|jpeg|svg|webp|ico)).*)",
  ],
};
