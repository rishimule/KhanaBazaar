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
// (8080), and next-intl / Next build redirect `Location` URLs carrying that
// internal port — `https://<host>:8080/...`. That port is unreachable from
// outside, so the browser hangs following the redirect. Strip the leaked port
// from same-origin redirect Locations (the hostname is already correct). Only
// runs behind a proxy (Cloud Run always sets `x-forwarded-for`), so local dev
// — which legitimately redirects to localhost:3000 — is untouched.
function externalizeRedirect(req: NextRequest, res: NextResponse): NextResponse {
  const location = res.headers.get("location");
  if (!location) return res;
  // x-forwarded-for is set by Cloud Run (and proxies generally); absent locally.
  if (!req.headers.get("x-forwarded-for")) return res;
  let url: URL;
  try {
    url = new URL(location, req.url);
  } catch {
    return res;
  }
  // Only touch redirects pointing back at our own origin that carry a port.
  if (url.hostname !== req.nextUrl.hostname || !url.port) return res;
  url.port = ""; // drop the internal :8080
  const proto = req.headers.get("x-forwarded-proto");
  if (proto) url.protocol = `${proto}:`;
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
