// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

/**
 * Trusted-device sign-in — client token coordinator.
 *
 * Single source of truth for the access (`kb_token`) and refresh (`kb_refresh`)
 * tokens in localStorage. Owns a single-flight `/auth/refresh` call, a proactive
 * pre-expiry refresh timer, and a listener registry so AuthContext can mirror the
 * access token into React state and run logout cleanup when a refresh fails.
 *
 * Framework-agnostic on purpose: `lib/api.ts` (outside React) triggers
 * refresh-on-401 through here without importing React.
 */
const ACCESS_KEY = "kb_token";
const REFRESH_KEY = "kb_refresh";
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REFRESH_LEAD_SECONDS = 60; // refresh this long before access-token expiry

type Listener = (accessToken: string | null) => void;
const listeners = new Set<Listener>();
let refreshInFlight: Promise<string | null> | null = null;
let refreshTimer: ReturnType<typeof setTimeout> | null = null;

function hasWindow(): boolean {
  return typeof window !== "undefined";
}

export function getAccessToken(): string | null {
  return hasWindow() ? localStorage.getItem(ACCESS_KEY) : null;
}

export function getRefreshToken(): string | null {
  return hasWindow() ? localStorage.getItem(REFRESH_KEY) : null;
}

function notify(accessToken: string | null): void {
  for (const fn of listeners) {
    try {
      fn(accessToken);
    } catch {
      /* a listener throwing must not break token bookkeeping */
    }
  }
}

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

function cancelTimer(): void {
  if (refreshTimer !== null) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

/** (Re)arm the proactive timer to refresh REFRESH_LEAD_SECONDS before expiry. */
function scheduleRefresh(expiresInSeconds: number): void {
  if (!hasWindow()) return;
  cancelTimer();
  const leadMs = Math.max(expiresInSeconds - REFRESH_LEAD_SECONDS, 5) * 1000;
  refreshTimer = setTimeout(() => {
    void refreshTokens();
  }, leadMs);
}

export function setTokens(
  access: string,
  refresh: string,
  expiresInSeconds = 900,
): void {
  if (!hasWindow()) return;
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
  scheduleRefresh(expiresInSeconds);
  notify(access);
}

export function clearTokens(): void {
  if (!hasWindow()) return;
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  cancelTimer();
  notify(null);
}

/** Base64url-decode the JWT payload and read `exp`. Returns true when the token
 * is absent, unparseable, or within `thresholdSeconds` of expiry. */
export function accessTokenExpiringSoon(thresholdSeconds = 120): boolean {
  const token = getAccessToken();
  if (!token) return true;
  try {
    const payload = token.split(".")[1];
    const json = JSON.parse(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
    ) as { exp?: number };
    if (typeof payload !== "string" || typeof json.exp !== "number") return true;
    const secondsLeft = json.exp - Math.floor(Date.now() / 1000);
    return secondsLeft <= thresholdSeconds;
  } catch {
    return true;
  }
}

/**
 * Rotate tokens via `/auth/refresh`. Single-flight: concurrent callers await the
 * same promise. Returns the new access token, or null on failure. A server (HTTP)
 * failure is definitive → tokens are cleared; a network error is transient →
 * tokens are kept for a later retry.
 */
export function refreshTokens(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  const refresh = getRefreshToken();
  if (!refresh) return Promise.resolve(null);

  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) {
        clearTokens(); // definitive: session invalid/revoked
        return null;
      }
      const data = (await res.json()) as {
        access_token: string;
        refresh_token: string;
        expires_in: number;
      };
      setTokens(data.access_token, data.refresh_token, data.expires_in);
      return data.access_token;
    } catch {
      return null; // network error: keep tokens, caller treats as transient
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}
