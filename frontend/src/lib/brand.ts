// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

/**
 * Single source of truth for the displayed brand name.
 * Set NEXT_PUBLIC_COMPANY_NAME (inlined at build time) to white-label;
 * falls back to "Khanabazaar".
 */
export const COMPANY_NAME =
  (process.env.NEXT_PUBLIC_COMPANY_NAME ?? "").trim() || "Khanabazaar";
