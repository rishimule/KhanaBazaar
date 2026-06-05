// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Dev Mailbox",
  robots: { index: false, follow: false },
};

export default function DevLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          fontFamily:
            "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
          background: "#0f1115",
          color: "#e6e6e6",
        }}
      >
        {children}
      </body>
    </html>
  );
}
