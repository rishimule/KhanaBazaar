// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  // Don't 308-strip a trailing slash before the rewrite fires. Backend
  // routes (FastAPI) are registered with a trailing slash, so stripping
  // it here triggers a backend 307 to the slashed URL using the upstream
  // host header — which leaks `https://localhost:8000` back to the phone.
  skipTrailingSlashRedirect: true,
  async rewrites() {
    // `:rest(.*)` captures the entire suffix verbatim, including any
    // trailing slash. `:path*` (segments-only) drops the trailing slash,
    // which we cannot afford because FastAPI's redirect_slashes then
    // bounces the request back with an upstream-host Location header.
    const apiInternal = process.env.API_INTERNAL_URL;
    if (apiInternal) {
      // Production: the web service proxies the versioned API to the internal
      // `api` Cloud Run service. /dev-logs is served by the real page (no proxy).
      return {
        beforeFiles: [],
        afterFiles: [
          { source: "/api/v1/:rest(.*)", destination: `${apiInternal}/api/v1/:rest` },
        ],
        fallback: [],
      };
    }
    // Local dev: proxy the API to the local backend, and the /dev-logs route to
    // the standalone log viewer. beforeFiles makes the proxy win over the
    // app/dev-logs/page.tsx file so local logs keep working.
    const logPort = process.env.LOG_VIEWER_PORT ?? "8001";
    return {
      beforeFiles: [
        { source: "/dev-logs", destination: `http://localhost:${logPort}/` },
        { source: "/dev-logs/:rest(.*)", destination: `http://localhost:${logPort}/:rest` },
      ],
      afterFiles: [
        { source: "/api/v1/:rest(.*)", destination: "http://localhost:8000/api/v1/:rest" },
      ],
      fallback: [],
    };
  },
};

export default withNextIntl(nextConfig);
