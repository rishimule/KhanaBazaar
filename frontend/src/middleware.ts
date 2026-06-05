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

// Behind Cloud Run (or any reverse proxy) the container listens on $PORT
// (8080), and next-intl / Next build redirect `Location` URLs from the
// internal request origin — leaking `:8080` into the host. The browser then
// follows the redirect to `https://<host>:8080/...`, which is unreachable from
// outside, so the page hangs. Rewrite same-origin redirect Locations to the
// external host. Only runs when `x-forwarded-proto` is present (i.e. behind a
// proxy), so local dev (no such header) is untouched.
function externalizeRedirect(req: NextRequest, res: NextResponse): NextResponse {
  const location = res.headers.get("location");
  if (!location) return res;
  const proto = req.headers.get("x-forwarded-proto");
  if (!proto) return res; // not behind a proxy (local dev) — leave as-is
  const host = req.headers.get("host"); // external host, preserved by Cloud Run
  if (!host) return res;
  let url: URL;
  try {
    url = new URL(location, req.url);
  } catch {
    return res;
  }
  // Only touch redirects pointing back at our own origin.
  if (url.hostname !== req.nextUrl.hostname) return res;
  url.protocol = `${proto}:`;
  url.host = host; // host header carries no internal :8080
  res.headers.set("location", url.toString());
  return res;
}

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
      return externalizeRedirect(req, NextResponse.redirect(target, 308));
    }
  }

  // Unprefixed operator / dev-logs paths: skip next-intl entirely so
  // it does not read or write the NEXT_LOCALE cookie on those routes.
  if (isI18nUnsupported(pathname)) {
    return NextResponse.next();
  }

  return externalizeRedirect(req, intlMiddleware(req));
}

export const config = {
  matcher: [
    "/((?!api|_next|favicon\\.ico|icons|manifest\\.json|sw\\.js|.*\\.(?:png|jpg|jpeg|svg|webp|ico)).*)",
  ],
};
