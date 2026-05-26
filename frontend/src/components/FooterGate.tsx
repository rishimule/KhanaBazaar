"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

// Locale-aware usePathname (from @/i18n/navigation) returns the path WITHOUT
// the locale prefix, so `/hi/account` resolves to `/account` and the dashboard
// prefixes below match in every locale — next/navigation's usePathname keeps
// the `/hi` prefix and would leak the footer onto non-English dashboards.
import { usePathname } from "@/i18n/navigation";
import Footer from "./Footer";

const DASHBOARD_PREFIXES = ["/account", "/seller", "/admin"];

export default function FooterGate() {
  const pathname = usePathname() ?? "";
  const hide = DASHBOARD_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
  if (hide) return null;
  return <Footer />;
}
