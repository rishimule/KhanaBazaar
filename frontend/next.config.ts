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
    //
    // In production the api lives at a different origin (Cloud Run), so the
    // proxy destination is read from INTERNAL_API_URL, baked at build time.
    // Dev falls back to the local backend.
    const apiBase = process.env.INTERNAL_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/v1/:rest(.*)",
        destination: `${apiBase}/api/v1/:rest`,
      },
      {
        source: "/dev-logs",
        destination: `http://localhost:${process.env.LOG_VIEWER_PORT ?? "8001"}/`,
      },
      {
        source: "/dev-logs/:rest(.*)",
        destination: `http://localhost:${process.env.LOG_VIEWER_PORT ?? "8001"}/:rest`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
