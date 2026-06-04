// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { Metadata } from "next";

import "@/app/globals.css";

// Standalone root layout for the deploy-only dev OTP inbox. Intentionally has
// no Auth/Cart/i18n providers — the page is self-contained and must not pull in
// customer/operator app context. This is a separate root layout (the app has no
// top-level layout.tsx; each route group / segment supplies its own <html>).
export const metadata: Metadata = {
  title: "Dev OTP inbox",
  robots: { index: false, follow: false },
};

export default function DevLogsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
