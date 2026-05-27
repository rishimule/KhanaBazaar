// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { patch } from "@/lib/api";

const ONE_YEAR = 60 * 60 * 24 * 365;

/** Write the NEXT_LOCALE cookie (read by the operator layout + api.ts). */
export function setLocaleCookie(locale: string): void {
  document.cookie = `NEXT_LOCALE=${locale}; path=/; max-age=${ONE_YEAR}; samesite=lax`;
}

/** Best-effort persist to User.preferred_language. No-op when unauthenticated.
 * Never throws — persistence must not block the in-page switch. */
export async function persistUserLanguage(
  locale: string,
  token: string | null,
): Promise<void> {
  if (!token) return;
  try {
    await patch("/api/v1/auth/me/language", { language: locale }, token);
  } catch {
    /* best-effort */
  }
}
