// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { patch } from "@/lib/api";
import {
  CUSTOMER_LOCALE_COOKIE,
  OPERATOR_LOCALE_COOKIE,
} from "@/lib/localeCookies";

const ONE_YEAR = 60 * 60 * 24 * 365;

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${name}=([^;]+)`),
  );
  return m ? m[1] : null;
}

function writeCookie(name: string, locale: string): void {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=${locale}; path=/; max-age=${ONE_YEAR}; samesite=lax`;
}

/** Write the operator locale cookie (read by the operator layout + api.ts on
 * operator routes). Returns whether the stored value actually changed, so the
 * caller can decide to refresh the current server-rendered view. */
export function setOperatorLocaleCookie(locale: string): boolean {
  const changed = readCookie(OPERATOR_LOCALE_COOKIE) !== locale;
  writeCookie(OPERATOR_LOCALE_COOKIE, locale);
  return changed;
}

/** Clear both locale cookies. Called on logout so a shared device doesn't leave
 * the next (guest) user on the previous user's language. Logged-in users
 * re-seed their locale from the saved preference on the next auth resolution. */
export function clearLocaleCookies(): void {
  if (typeof document === "undefined") return;
  for (const name of [CUSTOMER_LOCALE_COOKIE, OPERATOR_LOCALE_COOKIE]) {
    document.cookie = `${name}=; path=/; max-age=0; samesite=lax`;
  }
}

/** Best-effort persist to User.preferred_language (the single source of truth).
 * No-op when unauthenticated. Never throws — persistence must not block the
 * in-page switch. */
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
