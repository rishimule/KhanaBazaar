"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

/**
 * Last-resort boundary: fires when a layout itself throws, which a segment
 * error.tsx cannot catch.
 *
 * This repo has no root app/layout.tsx — each route group ((customer),
 * (operator), (dev)) owns its own <html>/<body> — and global-error replaces
 * whatever layout was rendering, so this file must emit its own document shell.
 *
 * Deliberately hardcoded English with inline styles: no NextIntlClientProvider
 * and no stylesheet are mounted at this point, so there is nothing to translate
 * with and no class names to rely on. This is the one screen in the product
 * where English-only is correct rather than i18n debt.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
          background: "#fff",
          color: "#1a1a1a",
        }}
      >
        <div
          role="alert"
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 12,
            minHeight: "100vh",
            padding: 24,
            textAlign: "center",
          }}
        >
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>
            Something went wrong
          </h1>
          <p style={{ margin: 0, maxWidth: "44ch", fontSize: 15, lineHeight: 1.55 }}>
            The app could not load this page. Nothing you saved was lost.
          </p>
          <button
            type="button"
            onClick={reset}
            style={{
              minHeight: 44,
              marginTop: 8,
              padding: "12px 24px",
              fontSize: 15,
              fontWeight: 600,
              color: "#fff",
              background: "#0F6B06",
              border: "1px solid #0F6B06",
              borderRadius: 8,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
          {/* A crash on a customer route lands here (there is no (customer)
              error.tsx), and this screen replaces the whole document — so
              without a link home the visitor has no navigation at all.

              Deliberately a plain <a>, not next/link: this boundary fires when
              a layout itself has thrown, which is exactly the state in which
              the client router is least trustworthy. A hard navigation always
              works. eslint-disable is the honest call here, not a shortcut. */}
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
          <a href="/" style={{ fontSize: 14, color: "#0F6B06" }}>
            Go to the home page
          </a>
          {error.digest && (
            <p style={{ margin: 0, fontSize: 12, color: "#666" }}>
              Reference: {error.digest}
            </p>
          )}
        </div>
      </body>
    </html>
  );
}
