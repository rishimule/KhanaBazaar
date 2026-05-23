"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { usePathname } from "next/navigation";
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
